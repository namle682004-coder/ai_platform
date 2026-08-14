using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;

namespace Everwin.AIPlatform.SDK
{
    /// <summary>
    /// Official Enterprise .NET 8 LTS Client SDK for AI Inference Platform (AIP).
    /// </summary>
    public class AIPClient
    {
        private readonly HttpClient _httpClient;
        public string ApiKey { get; }
        public string BaseUrl { get; }

        public AIPClient(string apiKey, string baseUrl = "http://localhost:8000")
        {
            ApiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
            BaseUrl = baseUrl.TrimEnd('/');

            _httpClient = new HttpClient
            {
                BaseAddress = new Uri(BaseUrl)
            };
            _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", ApiKey);
            _httpClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        }

        public async Task<JsonDocument?> CreateChatCompletionAsync(string model, string prompt)
        {
            var payload = new
            {
                model = model,
                messages = new[]
                {
                    new { role = "user", content = prompt }
                }
            };

            var response = await _httpClient.PostAsJsonAsync("/v1/chat/completions", payload);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>();
        }

        public async Task<JsonDocument?> CreateEmbeddingAsync(string model, string input)
        {
            var payload = new { model = model, input = input };
            var response = await _httpClient.PostAsJsonAsync("/v1/embeddings", payload);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>();
        }

        public async Task<JsonDocument?> CreateAsyncJobAsync(string jobType, string aliasName)
        {
            var payload = new { job_type = jobType, alias_name = aliasName };
            var response = await _httpClient.PostAsJsonAsync("/v1/jobs", payload);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<JsonDocument>();
        }
    }
}
