/* ==========================================================================
   🧠 SES Enterprise Gateway Client-Side Orchestrator
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // --- Application State ---
    const state = {
        activeApiKey: localStorage.getItem("ses_api_key") || "",
        activeNamespace: "personal_default",
        isAdmin: true,
        recentLogs: [],
        chartData: [12, 19, 3, 5, 2, 3, 10, 15, 8, 12, 20, 18], // Default mock traffic for initial draw
        healthPollInterval: null,
        metricsPollInterval: null
    };

    // Initialize API Key input UI
    const apiKeyInput = document.getElementById("active-api-key");
    if (apiKeyInput) {
        apiKeyInput.value = state.activeApiKey;
    }

    // --- UI Selectors ---
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanes = document.querySelectorAll(".tab-pane");
    const activeKeyRoleBadge = document.getElementById("active-key-role");
    const currentNamespaceIndicator = document.getElementById("current-namespace-indicator");

    // --- Toast Notification Helper ---
    function showToast(message, isError = false) {
        const toast = document.getElementById("toast-message");
        if (!toast) return;
        toast.querySelector(".toast-text").textContent = message;
        toast.className = `toast show${isError ? " error" : ""}`;
        setTimeout(() => {
            toast.classList.remove("show");
        }, 4000);
    }

    // --- API Request Helper ---
    async function apiRequest(endpoint, options = {}) {
        const headers = {
            "X-API-Key": state.activeApiKey,
            ...(options.headers || {})
        };
        
        if (!(options.body instanceof FormData) && typeof options.body === "object") {
            headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(options.body);
        }

        const fetchOptions = {
            ...options,
            headers
        };

        try {
            const response = await fetch(endpoint, fetchOptions);
            const contentType = response.headers.get("content-type");
            
            let data = null;
            if (contentType && contentType.includes("application/json")) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            if (!response.ok) {
                const errMsg = data?.detail || `HTTP Error ${response.status}`;
                throw new Error(errMsg);
            }
            return data;
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    }

    // --- Tab Switching Logic ---
    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const targetTab = item.getAttribute("data-tab");
            
            navItems.forEach(n => n.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));
            
            item.classList.add("active");
            const targetPane = document.getElementById(targetTab);
            if (targetPane) {
                targetPane.classList.add("active");
            }

            // Perform context-specific actions on tab view
            if (targetTab === "tab-overview") {
                fetchAnalytics();
            } else if (targetTab === "tab-documents") {
                fetchDocuments();
            } else if (targetTab === "tab-keys") {
                fetchApiKeys();
            }
        });
    });

    // Save Active Key Event
    const btnSaveKey = document.getElementById("btn-save-key");
    if (btnSaveKey) {
        btnSaveKey.addEventListener("click", () => {
            const newKey = apiKeyInput.value.trim();
            if (newKey) {
                state.activeApiKey = newKey;
                localStorage.setItem("ses_api_key", newKey);
                showToast("API Key updated and stored locally.");
                verifyCurrentKey();
            }
        });
    }

    // --- Key Verification and Permissions UI ---
    async function verifyCurrentKey() {
        try {
            // Check health & verify current key by requesting admin analytics
            const analytics = await apiRequest("/api/v1/admin/analytics");
            state.isAdmin = true;
            activeKeyRoleBadge.textContent = "Admin Mode";
            activeKeyRoleBadge.className = "key-badge role-admin";
            document.getElementById("nav-keys-btn").classList.remove("hidden");
            
            // Extract namespace from current credentials (we can query stats endpoint to inspect)
            const stats = await apiRequest("/api/v1/stats");
            state.activeNamespace = stats.namespace;
            currentNamespaceIndicator.innerHTML = `Active Namespace: <span>${stats.namespace}</span>`;
            
            // Draw analytics
            updateAnalyticsUI(analytics);
        } catch (error) {
            // If admin analytics request fails, key might be client role or invalid
            try {
                // Try client stats endpoint
                const stats = await apiRequest("/api/v1/stats");
                state.isAdmin = false;
                state.activeNamespace = stats.namespace;
                activeKeyRoleBadge.textContent = "Client Mode";
                activeKeyRoleBadge.className = "key-badge role-client";
                document.getElementById("nav-keys-btn").classList.add("hidden");
                currentNamespaceIndicator.innerHTML = `Active Namespace: <span>${stats.namespace}</span>`;
                
                // Hide admin things, trigger normal client metrics load
                fetchClientStats();
            } catch (err) {
                activeKeyRoleBadge.textContent = "Invalid Token";
                activeKeyRoleBadge.className = "key-badge status-error";
                showToast("The current API Key is invalid or rate limited. Please configure a valid credential.", true);
            }
        }
    }

    // --- Health Monitor Poller ---
    async function checkHealth() {
        const pills = {
            gateway: document.getElementById("health-gateway"),
            qdrant: document.getElementById("health-qdrant"),
            redis: document.getElementById("health-redis"),
            ollama: document.getElementById("health-ollama")
        };

        try {
            const health = await apiRequest("/api/v1/health");
            
            // Gateway health
            if (health.status === "healthy" || health.status === "degraded") {
                pills.gateway.className = "health-pill connected";
            } else {
                pills.gateway.className = "health-pill disconnected";
            }

            // Satellite services health
            const services = health.services || {};
            
            pills.qdrant.className = services.qdrant === "connected" ? "health-pill connected" : "health-pill disconnected";
            pills.redis.className = services.redis === "connected" ? "health-pill connected" : (services.redis === "disabled" ? "health-pill disabled" : "health-pill disconnected");
            pills.ollama.className = services.ollama_api === "connected" ? "health-pill connected" : "health-pill disconnected";
            
            // Update traffic chart data using real metrics over time
            if (state.recentLogs.length > 0) {
                state.chartData.push(state.recentLogs.length);
                if (state.chartData.length > 12) state.chartData.shift();
                drawTrafficChart();
            }
        } catch (error) {
            pills.gateway.className = "health-pill disconnected";
            pills.qdrant.className = "health-pill disconnected";
            pills.redis.className = "health-pill disconnected";
            pills.ollama.className = "health-pill disconnected";
        }
    }

    // --- Analytics Data Fetching ---
    async function fetchAnalytics() {
        if (!state.isAdmin) {
            fetchClientStats();
            return;
        }
        try {
            const analytics = await apiRequest("/api/v1/admin/analytics");
            updateAnalyticsUI(analytics);
        } catch (error) {
            console.error("Error loading analytics:", error);
        }
    }

    async function fetchClientStats() {
        try {
            const statsRes = await apiRequest("/api/v1/stats");
            const stats = statsRes.stats || {};
            
            document.getElementById("metric-requests").textContent = "-";
            document.getElementById("metric-searches").textContent = "-";
            document.getElementById("metric-ingestions").textContent = stats.total_documents || 0;
            document.getElementById("metric-latency").textContent = stats.rust_acceleration ? "Rust (Sub-ms)" : "Python (Normal)";
            
            // Draw empty / restricted placeholder overview
            const logsBody = document.querySelector("#logs-table tbody");
            logsBody.innerHTML = `<tr><td colspan="6" class="table-empty">Detailed log feeds are only visible to Administrator API keys.</td></tr>`;
            
            const perfContainer = document.getElementById("keys-performance-container");
            perfContainer.innerHTML = `<div class="empty-state">Role: Client. Analytics restricted.</div>`;
        } catch (error) {
            console.error("Failed to load client statistics:", error);
        }
    }

    function updateAnalyticsUI(data) {
        document.getElementById("metric-requests").textContent = data.total_requests || 0;
        document.getElementById("metric-searches").textContent = data.total_searches || 0;
        document.getElementById("metric-ingestions").textContent = data.total_ingestions || 0;
        
        let avgLat = data.average_latency_ms || 0.0;
        if (data.recent_logs && data.recent_logs.length > 0 && !data.average_latency_ms) {
            const latencies = data.recent_logs.map(l => l.latency_ms);
            avgLat = latencies.reduce((a, b) => a + b, 0) / latencies.length;
        }
        document.getElementById("metric-latency").textContent = `${avgLat.toFixed(1)} ms`;

        // Update Log Feed
        state.recentLogs = data.recent_logs || [];
        const logsBody = document.querySelector("#logs-table tbody");
        if (state.recentLogs.length === 0) {
            logsBody.innerHTML = `<tr><td colspan="6" class="table-empty">No requests logged yet. Waiting for API traffic...</td></tr>`;
        } else {
            logsBody.innerHTML = state.recentLogs.map(log => {
                const date = new Date(log.timestamp).toLocaleTimeString();
                const statusBadge = log.status_code < 400 
                    ? `<span class="badge status-200">${log.status_code} OK</span>`
                    : `<span class="badge status-error">${log.status_code} ERR</span>`;
                
                return `
                    <tr>
                        <td>${date}</td>
                        <td>${log.key_name}</td>
                        <td style="font-family: monospace;">${log.endpoint}</td>
                        <td><span class="key-badge">${log.namespace}</span></td>
                        <td>${statusBadge}</td>
                        <td><strong>${log.latency_ms.toFixed(1)} ms</strong></td>
                    </tr>
                `;
            }).join("");
        }

        // Update Client performance metrics
        const perfContainer = document.getElementById("keys-performance-container");
        const perfData = data.keys_performance || [];
        if (perfData.length === 0) {
            perfContainer.innerHTML = `<div class="empty-state">No key metrics tracked yet.</div>`;
        } else {
            perfContainer.innerHTML = perfData.map(keyPerf => `
                <div class="key-perf-row">
                    <div>
                        <div class="key-perf-name">${keyPerf.name}</div>
                        <div class="key-perf-meta">Namespace: ${keyPerf.namespace || 'global'}</div>
                    </div>
                    <div class="key-perf-stat">
                        <div class="key-perf-calls">${keyPerf.total_calls} calls</div>
                        <div class="key-perf-lat">Avg: ${keyPerf.avg_latency_ms ? keyPerf.avg_latency_ms.toFixed(1) : 0}ms</div>
                    </div>
                </div>
            `).join("");
        }
    }


    // --- TAB 2: RAG PLAYGROUND ---
    const btnRunQuery = document.getElementById("btn-run-query");
    const playgroundQuery = document.getElementById("playground-query");
    const playgroundAnswerOutput = document.getElementById("playground-answer-output");
    const playgroundSourcesOutput = document.getElementById("playground-sources-output");
    
    // Result panes tab switching
    const resultTabs = document.querySelectorAll(".result-tab");
    const resultPanes = document.querySelectorAll(".result-pane");
    resultTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            resultTabs.forEach(t => t.classList.remove("active"));
            resultPanes.forEach(p => p.classList.remove("active"));
            
            tab.classList.add("active");
            document.getElementById(tab.getAttribute("data-result-pane")).classList.add("active");
        });
    });

    if (btnRunQuery) {
        btnRunQuery.addEventListener("click", async () => {
            const query = playgroundQuery.value.trim();
            if (!query) {
                showToast("Please enter a query statement first.", true);
                return;
            }

            // Update UI State (Loading)
            btnRunQuery.disabled = true;
            btnRunQuery.querySelector(".btn-text").textContent = "Ingesting Core Context & Inferring...";
            btnRunQuery.querySelector(".spinner").classList.remove("hidden");
            
            playgroundAnswerOutput.innerHTML = `<div class="empty-state"><span class="spinner"></span> Running retrieval, re-ranking and local LLM synthesis...</div>`;
            playgroundSourcesOutput.innerHTML = `<div class="empty-state"><span class="spinner"></span> Fetching Qdrant reference coordinates...</div>`;

            // Switch to Answer tab view automatically
            resultTabs[0].click();

            const topK = parseInt(document.getElementById("playground-topk").value) || 5;
            const threshold = parseFloat(document.getElementById("playground-threshold").value) || 0.0;
            const generateAnswer = document.getElementById("playground-generate").checked;
            const modelOverride = document.getElementById("playground-model").value.trim() || null;

            try {
                const response = await apiRequest("/api/v1/search", {
                    method: "POST",
                    body: {
                        query,
                        top_k: topK,
                        threshold,
                        generate_answer: generateAnswer,
                        model_override: modelOverride
                    }
                });

                // Display answer
                if (response.answer) {
                    // Simple Markdown-to-HTML parser (handles bold, code, lists and paragraphs)
                    const parsedAnswer = parseMarkdownToHTML(response.answer);
                    playgroundAnswerOutput.innerHTML = `
                        <div class="answer-header" style="margin-bottom:15px; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:10px;">
                            <span class="key-badge" style="background-color:rgba(99, 102, 241, 0.15); color:var(--accent-indigo)">Ollama Model: ${modelOverride || "llama3.2"}</span>
                            <span class="key-badge" style="background-color:rgba(16, 185, 129, 0.15); color:var(--accent-emerald)">Time: ${response.total_time_ms.toFixed(0)}ms</span>
                            <span class="key-badge" style="background-color:rgba(6, 182, 212, 0.15); color:var(--accent-cyan)">Engine: ${response.rust_accelerated ? "Rust Hybrid" : "Python Core"}</span>
                        </div>
                        <div class="markdown-body">${parsedAnswer}</div>
                    `;
                } else {
                    playgroundAnswerOutput.innerHTML = `<div class="empty-state">No LLM answer was synthesized (RAG Search only). Check Qdrant sources.</div>`;
                }

                // Display source chunks
                const docs = response.results || [];
                if (docs.length === 0) {
                    playgroundSourcesOutput.innerHTML = `<div class="empty-state">No matching documents passed the threshold constraint.</div>`;
                } else {
                    playgroundSourcesOutput.innerHTML = docs.map((doc, idx) => {
                        const meta = doc.metadata || {};
                        const filename = meta.filename || "Unknown Source";
                        const relevance = doc.score ? (doc.score * 100).toFixed(1) + "%" : "N/A";
                        
                        return `
                            <div class="source-card">
                                <div class="source-header">
                                    <span class="source-title">[${idx + 1}] ${filename}</span>
                                    <span class="source-score">${relevance} match</span>
                                </div>
                                <p class="source-text">"${doc.text}"</p>
                                <div class="source-footer">
                                    <span>Indexed: ${new Date(doc.indexed_at * 1000).toLocaleDateString()}</span>
                                    <span>Metadata: page_number: ${meta.page_number || 'N/A'}, author: ${meta.author || 'unknown'}</span>
                                </div>
                            </div>
                        `;
                    }).join("");
                }

                showToast("Search & Inference completed successfully.");
            } catch (error) {
                playgroundAnswerOutput.innerHTML = `<div class="empty-state" style="color:var(--accent-crimson);">Error: ${error.message}</div>`;
                playgroundSourcesOutput.innerHTML = `<div class="empty-state" style="color:var(--accent-crimson);">Failed to fetch search points.</div>`;
                showToast(`Playground query failed: ${error.message}`, true);
            } finally {
                btnRunQuery.disabled = false;
                btnRunQuery.querySelector(".btn-text").textContent = "Execute Retrieval & Generation";
                btnRunQuery.querySelector(".spinner").classList.add("hidden");
            }
        });
    }

    function parseMarkdownToHTML(md) {
        let html = md;
        // Code Blocks
        html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        // Inline Code
        html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
        // Bold
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // List items
        html = html.replace(/^\s*-\s+(.+)$/gm, '<li>$1</li>');
        // Wrap lists
        html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        // Paragraphs
        html = html.replace(/\n\n([^#\n]+)/g, '<p>$1</p>');
        
        return html;
    }


    // --- TAB 3: DOCUMENT LIBRARY MANAGER ---
    const dropZone = document.getElementById("file-drop-zone");
    const fileInput = document.getElementById("ingest-file-input");
    const fileDetailsBox = document.getElementById("file-details-box");
    const selectedFileName = document.getElementById("selected-file-name");
    const selectedFileSize = document.getElementById("selected-file-size");
    const fileMetadataInput = document.getElementById("file-metadata-json");
    const btnUploadFile = document.getElementById("btn-upload-file");

    // Ingest tabs toggle
    const ingestTabs = document.querySelectorAll(".ingest-tab");
    const ingestContents = document.querySelectorAll(".ingest-content");
    ingestTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            ingestTabs.forEach(t => t.classList.remove("active"));
            ingestContents.forEach(c => c.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById(tab.getAttribute("data-ingest-mode")).classList.add("active");
        });
    });

    let currentFile = null;

    if (dropZone) {
        dropZone.addEventListener("click", () => fileInput.click());
        
        dropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropZone.classList.add("dragover");
        });
        
        dropZone.addEventListener("dragleave", () => {
            dropZone.classList.remove("dragover");
        });
        
        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
            if (e.dataTransfer.files.length > 0) {
                handleFileSelect(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener("change", () => {
            if (fileInput.files.length > 0) {
                handleFileSelect(fileInput.files[0]);
            }
        });
    }

    function handleFileSelect(file) {
        currentFile = file;
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = `${(file.size / 1024).toFixed(1)} KB`;
        fileDetailsBox.classList.remove("hidden");
        btnUploadFile.disabled = false;
    }

    if (btnUploadFile) {
        btnUploadFile.addEventListener("click", async () => {
            if (!currentFile) return;

            btnUploadFile.disabled = true;
            btnUploadFile.querySelector(".spinner").classList.remove("hidden");

            const formData = new FormData();
            formData.append("file", currentFile);
            
            const metaStr = fileMetadataInput.value.trim();
            if (metaStr) {
                formData.append("metadata_json", metaStr);
            }

            try {
                const response = await apiRequest("/api/v1/ingest/file", {
                    method: "POST",
                    body: formData
                });
                
                showToast(`Successfully ingested: ${currentFile.name}`);
                
                // Clear state
                currentFile = null;
                fileInput.value = "";
                fileDetailsBox.classList.add("hidden");
                fileMetadataInput.value = "";
                btnUploadFile.disabled = true;
                
                // Refresh library list
                fetchDocuments();
                fetchAnalytics();
            } catch (error) {
                showToast(`Ingestion failed: ${error.message}`, true);
            } finally {
                btnUploadFile.disabled = false;
                btnUploadFile.querySelector(".spinner").classList.add("hidden");
            }
        });
    }

    // Ingest Raw Text
    const btnUploadText = document.getElementById("btn-upload-text");
    if (btnUploadText) {
        btnUploadText.addEventListener("click", async () => {
            const title = document.getElementById("text-ingest-title").value.trim();
            const text = document.getElementById("text-ingest-body").value.trim();
            const metaStr = document.getElementById("text-ingest-metadata").value.trim();

            if (!title || !text) {
                showToast("Title and Text body are required.", true);
                return;
            }

            let metadata = {};
            if (metaStr) {
                try {
                    metadata = json.parse(metaStr);
                } catch (e) {
                    showToast("Metadata must be valid JSON.", true);
                    return;
                }
            }

            btnUploadText.disabled = true;
            btnUploadText.querySelector(".spinner").classList.remove("hidden");

            try {
                await apiRequest("/api/v1/ingest/text", {
                    method: "POST",
                    body: {
                        text,
                        filename: title,
                        metadata
                    }
                });

                showToast(`Successfully indexed: ${title}`);
                document.getElementById("text-ingest-title").value = "";
                document.getElementById("text-ingest-body").value = "";
                document.getElementById("text-ingest-metadata").value = "";
                
                fetchDocuments();
                fetchAnalytics();
            } catch (error) {
                showToast(`Indexing failed: ${error.message}`, true);
            } finally {
                btnUploadText.disabled = false;
                btnUploadText.querySelector(".spinner").classList.add("hidden");
            }
        });
    }

    // Load Documents Library
    async function fetchDocuments() {
        const tableBody = document.querySelector("#documents-table tbody");
        tableBody.innerHTML = `<tr><td colspan="5" class="table-empty"><span class="spinner"></span> Loading library documents...</td></tr>`;

        try {
            const response = await apiRequest("/api/v1/documents");
            const docs = response.documents || [];
            
            if (docs.length === 0) {
                tableBody.innerHTML = `<tr><td colspan="5" class="table-empty">No documents found inside namespace: ${state.activeNamespace}</td></tr>`;
            } else {
                tableBody.innerHTML = docs.map(doc => {
                    const meta = doc.metadata || {};
                    const filename = meta.filename || doc.id;
                    const dateStr = doc.indexed_at 
                        ? new Date(doc.indexed_at * 1000).toLocaleString() 
                        : "N/A";
                    const uploader = meta.uploaded_by || "system";
                    const snippet = doc.text_snippet || "No preview content";
                    
                    return `
                        <tr>
                            <td style="font-weight:600; color:var(--text-primary);">${filename}</td>
                            <td style="font-style:italic; font-size:0.8rem; max-width: 250px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">"${snippet}"</td>
                            <td>${uploader}</td>
                            <td>${dateStr}</td>
                            <td>
                                <button class="btn-danger btn-delete-doc" data-doc-id="${doc.id}">Delete</button>
                            </td>
                        </tr>
                    `;
                }).join("");

                // Hook up delete buttons
                document.querySelectorAll(".btn-delete-doc").forEach(btn => {
                    btn.addEventListener("click", async () => {
                        const docId = btn.getAttribute("data-doc-id");
                        if (confirm(`Are you sure you want to delete document: ${docId}?`)) {
                            try {
                                await apiRequest(`/api/v1/documents/${docId}`, {
                                    method: "DELETE"
                                });
                                showToast("Document successfully deleted from Qdrant vector spaces.");
                                fetchDocuments();
                                fetchAnalytics();
                            } catch (e) {
                                showToast(`Delete failed: ${e.message}`, true);
                            }
                        }
                    });
                });
            }
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="5" class="table-empty" style="color:var(--accent-crimson);">Error: ${error.message}</td></tr>`;
        }
    }

    const btnRefreshDocs = document.getElementById("btn-refresh-docs");
    if (btnRefreshDocs) {
        btnRefreshDocs.addEventListener("click", () => fetchDocuments());
    }


    // --- TAB 4: API ACCESS KEY MANAGER ---
    const btnCreateKey = document.getElementById("btn-create-key");
    const keyNameInput = document.getElementById("new-key-name");
    const keyNamespaceInput = document.getElementById("new-key-namespace");
    const keyLimitInput = document.getElementById("new-key-ratelimit");
    const keyRoleSelect = document.getElementById("new-key-role");

    async function fetchApiKeys() {
        if (!state.isAdmin) return;
        
        const tableBody = document.querySelector("#keys-table tbody");
        tableBody.innerHTML = `<tr><td colspan="6" class="table-empty"><span class="spinner"></span> Loading authorized API keys...</td></tr>`;

        try {
            const response = await apiRequest("/api/v1/admin/keys");
            const keys = response.keys || [];

            tableBody.innerHTML = keys.map(keyData => {
                const dateStr = new Date(keyData.created_at * 1000).toLocaleDateString();
                const roleClass = keyData.role === "admin" ? "badge role-admin" : "badge role-client";
                
                return `
                    <tr>
                        <td>
                            <strong>${keyData.name}</strong>
                            <div style="font-size:0.75rem; color:var(--text-muted);">Created: ${dateStr}</div>
                        </td>
                        <td><span class="key-badge">${keyData.namespace}</span></td>
                        <td><span class="${roleClass}">${keyData.role}</span></td>
                        <td>${keyData.rate_limit} req/min</td>
                        <td style="font-family:monospace; font-size:0.8rem;">
                            <span class="key-text" style="background-color:var(--bg-tertiary); padding:4px 8px; border-radius:4px;">${keyData.key}</span>
                        </td>
                        <td>
                            <button class="btn-danger btn-delete-key" data-key="${keyData.key}">Revoke</button>
                        </td>
                    </tr>
                `;
            }).join("");

            // Hook up revoke buttons
            document.querySelectorAll(".btn-delete-key").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const keyToRevoke = btn.getAttribute("data-key");
                    if (confirm("WARNING: Are you sure you want to revoke commercial access for this key?")) {
                        try {
                            await apiRequest(`/api/v1/admin/keys/${keyToRevoke}`, {
                                method: "DELETE"
                            });
                            showToast("API Access key revoked successfully.");
                            fetchApiKeys();
                        } catch (e) {
                            showToast(`Revocation failed: ${e.message}`, true);
                        }
                    }
                });
            });
        } catch (error) {
            tableBody.innerHTML = `<tr><td colspan="6" class="table-empty" style="color:var(--accent-crimson);">Error loading tokens: ${error.message}</td></tr>`;
        }
    }

    if (btnCreateKey) {
        btnCreateKey.addEventListener("click", async () => {
            const name = keyNameInput.value.trim();
            const namespace = keyNamespaceInput.value.trim();
            const limit = parseInt(keyLimitInput.value);
            const role = keyRoleSelect.value;

            if (!name || !namespace) {
                showToast("Client Name and Namespace are required.", true);
                return;
            }

            btnCreateKey.disabled = true;
            btnCreateKey.querySelector(".spinner").classList.remove("hidden");

            try {
                await apiRequest("/api/v1/admin/keys", {
                    method: "POST",
                    body: {
                        name,
                        namespace,
                        rate_limit: limit,
                        role
                    }
                });

                showToast(`API Key successfully generated for ${name}.`);
                keyNameInput.value = "";
                keyNamespaceInput.value = "personal_default";
                keyLimitInput.value = "60";
                
                fetchApiKeys();
            } catch (error) {
                showToast(`Creation failed: ${error.message}`, true);
            } finally {
                btnCreateKey.disabled = false;
                btnCreateKey.querySelector(".spinner").classList.add("hidden");
            }
        });
    }

    // --- HTML5 CANVAS TRAFFIC CHART DRAWING ---
    function drawTrafficChart() {
        const canvas = document.getElementById("traffic-chart");
        if (!canvas) return;
        
        const ctx = canvas.getContext("2d");
        const width = canvas.width;
        const height = canvas.height;
        
        // Clear canvas
        ctx.clearRect(0, 0, width, height);
        
        // Draw grid lines
        ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = 20 + i * (height - 40) / 4;
            ctx.beginPath();
            ctx.moveTo(20, y);
            ctx.lineTo(width - 20, y);
            ctx.stroke();
        }
        
        const data = state.chartData;
        const maxData = Math.max(...data, 5);
        const paddingLeft = 30;
        const paddingRight = 30;
        const chartHeight = height - 60;
        const stepX = (width - paddingLeft - paddingRight) / (data.length - 1);
        
        // Fill gradient
        const fillGrad = ctx.createLinearGradient(0, 0, 0, height);
        fillGrad.addColorStop(0, "rgba(99, 102, 241, 0.3)");
        fillGrad.addColorStop(1, "rgba(6, 182, 212, 0)");
        
        // Line gradient
        const lineGrad = ctx.createLinearGradient(0, 0, width, 0);
        lineGrad.addColorStop(0, "#4f46e5");
        lineGrad.addColorStop(1, "#06b6d4");
        
        // Draw line & fill paths
        ctx.beginPath();
        data.forEach((val, i) => {
            const x = paddingLeft + i * stepX;
            const y = height - 30 - (val / maxData) * chartHeight;
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        });
        
        // Set stroke options
        ctx.strokeStyle = lineGrad;
        ctx.lineWidth = 3;
        ctx.shadowColor = "rgba(99, 102, 241, 0.5)";
        ctx.shadowBlur = 10;
        ctx.stroke();
        ctx.shadowBlur = 0; // reset shadow
        
        // Draw fill under the line
        ctx.lineTo(paddingLeft + (data.length - 1) * stepX, height - 30);
        ctx.lineTo(paddingLeft, height - 30);
        ctx.closePath();
        ctx.fillStyle = fillGrad;
        ctx.fill();
        
        // Draw data point circles
        data.forEach((val, i) => {
            const x = paddingLeft + i * stepX;
            const y = height - 30 - (val / maxData) * chartHeight;
            
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, Math.PI * 2);
            ctx.fillStyle = "#ffffff";
            ctx.fill();
            ctx.strokeStyle = "#4f46e5";
            ctx.lineWidth = 2;
            ctx.stroke();
        });
    }

    // Clear logs button
    const btnClearLogs = document.getElementById("btn-clear-logs");
    if (btnClearLogs) {
        btnClearLogs.addEventListener("click", () => {
            if (confirm("Are you sure you want to clear the logs view? This does not delete actual traffic data.")) {
                state.recentLogs = [];
                const logsBody = document.querySelector("#logs-table tbody");
                logsBody.innerHTML = `<tr><td colspan="6" class="table-empty">No requests logged yet. Waiting for API traffic...</td></tr>`;
                showToast("Dashboard log display cleared.");
            }
        });
    }

    // --- INITIALIZE PAGE ---
    verifyCurrentKey();
    checkHealth();
    drawTrafficChart();
    
    // Set polling timers (e.g. 10s health checks, 12s analytics fetch)
    state.healthPollInterval = setInterval(checkHealth, 10000);
    state.metricsPollInterval = setInterval(fetchAnalytics, 12000);
});
