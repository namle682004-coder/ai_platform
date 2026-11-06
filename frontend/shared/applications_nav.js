(function (window) {
    'use strict';

    window.AIP_APPLICATION_NAV_GROUPS = [
        {
            id: 'language',
            label: 'Language & LLM',
            items: [
                ['RAG Chatbot', 'fa-brain', 'rag-chatbot'],
                ['LLM Chatbot', 'fa-comments', 'llm-chat'],
                ['Moderation API', 'fa-shield', 'moderation'],
                ['Text Embeddings', 'fa-diagram-project', 'embeddings'],
                ['Text Summarization', 'fa-align-left', 'summarization'],
                ['Translation', 'fa-language', 'translation'],
            ],
        },
        {
            id: 'speech',
            label: 'Speech & Audio',
            items: [
                ['Speech to Text', 'fa-microphone', 'speech-to-text'],
                ['Text to Speech', 'fa-volume-high', 'text-to-speech'],
            ],
        },
        {
            id: 'vision',
            label: 'Vision & OCR',
            items: [
                ['Image Gen API', 'fa-image', 'image-generation'],
                ['ID Recognition', 'fa-id-card', 'ocr-cccd'],
                ["Driver's License", 'fa-address-card', 'ocr-driver-license'],
                ['Passport Recognition', 'fa-passport', 'ocr-passport'],
                ['FaceMatch', 'fa-face-smile', 'face-match'],
                ['Liveness', 'fa-eye', 'liveness'],
            ],
        },
    ];

    // Item ids are service slugs (URL: /projects/{project}/services/{slug}); AipRoutes (project_routes.js)
    // maps the former endpoint ids and knows which services are live.
    window.isApiLive = function (apiId) {
        return !!(window.AipRoutes && window.AipRoutes.isServiceLive(apiId));
    };

    // A service that is not live yet has its URL too: the server answers it with the "in development" page.
    window.aipProjectApiHref = function (apiId) {
        return window.AipRoutes ? window.AipRoutes.serviceHref(apiId) : `/services/${encodeURIComponent(apiId)}`;
    };
})(window);
