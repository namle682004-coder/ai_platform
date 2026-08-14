# Everwin.AIPlatform.SDK (.NET 8 LTS Client SDK)

Official Enterprise .NET 8 LTS Client SDK for the AI Inference Platform (AIP).

## Installation

```bash
dotnet add package Everwin.AIPlatform.SDK
```

## Quickstart Usage (C# .NET 8)

```csharp
using Everwin.AIPlatform.SDK;

var client = new AIPClient(
    apiKey: "aip_live_your_api_key_here",
    baseUrl: "http://localhost:8000"
);

// 1. Chat Completion API
var chatResult = await client.CreateChatCompletionAsync(
    model: "chat-general-standard",
    prompt: "Xin chào từ ứng dụng C# .NET 8!"
);

// 2. Vector Embedding API
var embedResult = await client.CreateEmbeddingAsync(
    model: "embed-standard",
    input: "Nền tảng AI Inference Platform"
);

// 3. Create Async Job API
var jobResult = await client.CreateAsyncJobAsync(
    jobType: "video_generation",
    aliasName: "video-gen-standard"
);
```
