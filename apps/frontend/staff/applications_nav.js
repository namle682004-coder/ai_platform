(function (window) {
    'use strict';

    window.AIP_APPLICATION_NAV_GROUPS = [
        {
            id: 'language',
            label: 'Language & LLM',
            items: [
                ['LLM Chatbot', 'fa-comments', 'efb24a03-059d-440c-bd35-0b5b3a776983'],
                ['Moderation API', 'fa-shield', 'a5b8e6f7-9154-4c65-d816-e42705f43678'],
                ['Text Embeddings', 'fa-diagram-project', 'd8eb19ca-2487-4f98-0b49-175038c76901'],
                ['Text Summarization', 'fa-align-left', 'fa0d3bec-46a9-41ba-2d6b-39725ae98123'],
                ['Translation', 'fa-language', 'e9fc2adb-3598-40a9-1c5a-286149d87012'],
            ],
        },
        {
            id: 'speech',
            label: 'Speech & Audio',
            items: [
                ['Speech to Text', 'fa-microphone', '3a72d1f9-46c8-472e-8395-cb091a136701'],
                ['Text to Speech', 'fa-volume-high', '8b51ef94-912a-4367-bf16-36701a09cb12'],
            ],
        },
        {
            id: 'vision',
            label: 'Vision & OCR',
            items: [
                ['Image Gen API', 'fa-image', 'f4a7d5e6-8043-4b54-c705-d31694e32567'],
                ['ID Recognition', 'fa-id-card', 'c194a2b3-5710-4821-9472-a08361b09234'],
                ["Driver's License", 'fa-address-card', 'd285b3c4-6821-4932-a583-b19472c10345'],
                ['Passport Recognition', 'fa-passport', 'e396c4d5-7932-4a43-b694-c20583d21456'],
                ['FaceMatch', 'fa-face-smile', 'b6c9f7a8-0265-4d76-e927-f53816a54789'],
                ['Liveness', 'fa-eye', 'c7da08b9-1376-4e87-fa38-064927b65890'],
            ],
        },
    ];

    window.aipProjectApiHref = function (apiId) {
        const projectInPath = window.location.pathname.match(/^\/project\/([^/]+)/i);
        let projectId = projectInPath ? projectInPath[1] : localStorage.getItem('aip_active_project_id');
        if (!projectId) {
            try {
                const projects = JSON.parse(localStorage.getItem('aip_projects') || '[]');
                const activeName = localStorage.getItem('aip_active_project');
                projectId = projects.find(project => project.project_name === activeName)?.project_id ||
                    projects[0]?.project_id;
            } catch (error) {
                console.error('Unable to determine the active project for API navigation.', error);
            }
        }
        projectId ||= 'f40b6a70-ea64-4d01-90dc-53a2d7a81395';
        return `/project/${encodeURIComponent(projectId)}/apis/${encodeURIComponent(apiId)}`;
    };
})(window);
