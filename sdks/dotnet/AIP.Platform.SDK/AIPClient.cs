using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Polly;
using Polly.CircuitBreaker;
using Polly.Retry;

namespace AIP.Platform.SDK
{
    /// <summary>
    /// Official Enterprise .NET 8 LTS Client SDK for AI Inference Platform (AIP).
    /// Implements:
    /// - Polly Resilience: Retries with exponential backoff on 429/503/504 and Circuit Breaker
    /// - SSE Streaming: Real-time chunk parser for LLM Chat & Audio Speech
    /// - Async Job Helpers: Idempotent job creation, polling, cancellation, and artifact download
    /// Compliant with SRS Section 4.4 (.NET SDK).
    /// </summary>
    public class AIPClient
    {
        private readonly HttpClient _httpClient;
        private readonly ResiliencePipeline<HttpResponseMessage> _resiliencePipeline;

        public string ApiKey { get; }
        public string BaseUrl { get; }

        public AIPClient(string apiKey, string baseUrl = "http://localhost:8000", HttpClient? customHttpClient = null)
        {
            ApiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
            BaseUrl = baseUrl.TrimEnd('/');

            _httpClient = customHttpClient ?? new HttpClient
            {
                BaseAddress = new Uri(BaseUrl),
                Timeout = TimeSpan.FromSeconds(120)
            };

            _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", ApiKey);
            _httpClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

            // SRS Section 4.4 Resilience: Polly retry with exponential backoff + circuit breaker
            _resiliencePipeline = new ResiliencePipelineBuilder<HttpResponseMessage>()
                .AddRetry(new RetryStrategyOptions<HttpResponseMessage>
                {
                    MaxRetryAttempts = 3,
                    Delay = TimeSpan.FromMilliseconds(500),
                    BackoffType = DelayBackoffType.Exponential,
                    UseJitter = true,
                    ShouldHandle = new PredicateBuilder<HttpResponseMessage>()
                        .HandleResult(response =>
                            response.StatusCode == System.Net.HttpStatusCode.TooManyRequests || // 429
                            response.StatusCode == System.Net.HttpStatusCode.ServiceUnavailable || // 503
                            response.StatusCode == System.Net.HttpStatusCode.GatewayTimeout) // 504
                })
                .AddCircuitBreaker(new CircuitBreakerStrategyOptions<HttpResponseMessage>
                {
                    FailureRatio = 0.5,
                    SamplingDuration = TimeSpan.FromSeconds(30),
                    MinimumThroughput = 8,
                    BreakDuration = TimeSpan.FromSeconds(15),
                    ShouldHandle = new PredicateBuilder<HttpResponseMessage>()
                        .HandleResult(response => response.StatusCode == System.Net.HttpStatusCode.ServiceUnavailable)
                })
                .Build();
        }

        #region 1. Synchronous Inference

        /// <summary>
        /// OpenAI-compatible Chat Completion (/v1/chat/completions)
        /// </summary>
        public async Task<JsonDocument?> CreateChatCompletionAsync(string model, string prompt, CancellationToken cancellationToken = default)
        {
            var payload = new
            {
                model = model,
                messages = new[] { new { role = "user", content = prompt } },
                stream = false
            };

            var response = await _resiliencePipeline.ExecuteAsync(
                async ct => await _httpClient.PostAsJsonAsync("/v1/chat/completions", payload, ct),
                cancellationToken
            );

            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken: cancellationToken);
        }

        /// <summary>
        /// Dense Vector Embeddings (/v1/embeddings)
        /// </summary>
        public async Task<JsonDocument?> CreateEmbeddingAsync(string model, string input, CancellationToken cancellationToken = default)
        {
            var payload = new { model = model, input = input };

            var response = await _resiliencePipeline.ExecuteAsync(
                async ct => await _httpClient.PostAsJsonAsync("/v1/embeddings", payload, ct),
                cancellationToken
            );

            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken: cancellationToken);
        }

        /// <summary>
        /// Content Moderation & Policy Enforcement (/v1/moderations)
        /// </summary>
        public async Task<JsonDocument?> CheckModerationAsync(string input, string? model = null, CancellationToken cancellationToken = default)
        {
            var payload = new { input = input, model = model ?? "moderation-multimodal" };

            var response = await _resiliencePipeline.ExecuteAsync(
                async ct => await _httpClient.PostAsJsonAsync("/v1/moderations", payload, ct),
                cancellationToken
            );

            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken: cancellationToken);
        }

        #endregion

        #region 2. SSE Streaming (SRS Section 3.2 & 4.4)

        /// <summary>
        /// Real-time Server-Sent Events (SSE) streaming for Chat Completions.
        /// Yields content chunks progressively until [DONE].
        /// </summary>
        public async IAsyncEnumerable<string> CreateChatCompletionStreamAsync(
            string model,
            string prompt,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var payload = new
            {
                model = model,
                messages = new[] { new { role = "user", content = prompt } },
                stream = true
            };

            var request = new HttpRequestMessage(HttpMethod.Post, "/v1/chat/completions")
            {
                Content = JsonContent.Create(payload)
            };
            request.Headers.Accept.Clear();
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("text/event-stream"));

            using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            response.EnsureSuccessStatusCode();

            using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
            using var reader = new StreamReader(stream);

            while (!reader.EndOfStream && !cancellationToken.IsCancellationRequested)
            {
                var line = await reader.ReadLineAsync(cancellationToken);
                if (string.IsNullOrWhiteSpace(line)) continue;

                if (line.StartsWith("data: "))
                {
                    var data = line.Substring(6).Trim();
                    if (data == "[DONE]") break;

                    string? contentChunk = null;
                    try
                    {
                        using var doc = JsonDocument.Parse(data);
                        if (doc.RootElement.TryGetProperty("choices", out var choices) && choices.GetArrayLength() > 0)
                        {
                            var delta = choices[0].GetProperty("delta");
                            if (delta.TryGetProperty("content", out var contentProp))
                            {
                                contentChunk = contentProp.GetString();
                            }
                        }
                    }
                    catch (JsonException)
                    {
                        contentChunk = data;
                    }

                    if (!string.IsNullOrEmpty(contentChunk))
                    {
                        yield return contentChunk;
                    }
                }
            }
        }

        #endregion

        #region 3. Async Job Helpers (SRS Section 3.3, 4.4 & Section 7)

        /// <summary>
        /// Creates an asynchronous heavy job (/v1/jobs) with mandatory Idempotency-Key.
        /// </summary>
        public async Task<JsonDocument?> CreateAsyncJobAsync(
            string jobType,
            string aliasName,
            string? idempotencyKey = null,
            object? extraParams = null,
            CancellationToken cancellationToken = default)
        {
            var key = idempotencyKey ?? Guid.NewGuid().ToString("N");
            var payload = new Dictionary<string, object>
            {
                ["job_type"] = jobType,
                ["alias_name"] = aliasName
            };

            if (extraParams != null)
            {
                var json = JsonSerializer.Serialize(extraParams);
                var dict = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                if (dict != null)
                {
                    foreach (var kvp in dict) payload[kvp.Key] = kvp.Value;
                }
            }

            var request = new HttpRequestMessage(HttpMethod.Post, "/v1/jobs")
            {
                Content = JsonContent.Create(payload)
            };
            request.Headers.Add("Idempotency-Key", key);

            var response = await _resiliencePipeline.ExecuteAsync(
                async ct => await _httpClient.SendAsync(request, ct),
                cancellationToken
            );

            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken: cancellationToken);
        }

        /// <summary>
        /// Retrieves the current status and progress of an asynchronous job (/v1/jobs/{id})
        /// </summary>
        public async Task<JsonDocument?> GetJobStatusAsync(string jobId, CancellationToken cancellationToken = default)
        {
            var response = await _httpClient.GetAsync($"/v1/jobs/{jobId}", cancellationToken);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken: cancellationToken);
        }

        /// <summary>
        /// Cancels a queued or running job (/v1/jobs/{id}/cancel)
        /// </summary>
        public async Task<bool> CancelJobAsync(string jobId, CancellationToken cancellationToken = default)
        {
            var response = await _httpClient.PostAsync($"/v1/jobs/{jobId}/cancel", null, cancellationToken);
            return response.IsSuccessStatusCode;
        }

        /// <summary>
        /// Polls job status until it reaches 'completed' or 'failed', with automatic interval delay.
        /// </summary>
        public async Task<JsonDocument?> WaitForJobCompletionAsync(
            string jobId,
            TimeSpan? pollInterval = null,
            TimeSpan? maxTimeout = null,
            CancellationToken cancellationToken = default)
        {
            var interval = pollInterval ?? TimeSpan.FromSeconds(2);
            var timeout = maxTimeout ?? TimeSpan.FromMinutes(10);
            var startTime = DateTime.UtcNow;

            while (!cancellationToken.IsCancellationRequested)
            {
                if (DateTime.UtcNow - startTime > timeout)
                {
                    throw new TimeoutException($"Job {jobId} did not complete within the timeout of {timeout.TotalSeconds} seconds.");
                }

                var statusDoc = await GetJobStatusAsync(jobId, cancellationToken);
                if (statusDoc != null && statusDoc.RootElement.TryGetProperty("status", out var statusProp))
                {
                    var status = statusProp.GetString();
                    if (status == "completed" || status == "failed" || status == "cancelled")
                    {
                        return statusDoc;
                    }
                }

                await Task.Delay(interval, cancellationToken);
            }

            return null;
        }

        /// <summary>
        /// Retrieves pre-signed download URLs for completed job artifacts (/v1/jobs/{id}/result)
        /// </summary>
        public async Task<JsonDocument?> GetJobResultAsync(string jobId, CancellationToken cancellationToken = default)
        {
            var response = await _httpClient.GetAsync($"/v1/jobs/{jobId}/result", cancellationToken);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>(cancellationToken: cancellationToken);
        }

        #endregion
    }
}
