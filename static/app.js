/**
 * Document Router Platform — Frontend Logic
 *
 * Handles: drag-drop upload, API calls, result cards, jobs table, toasts
 */

const API_BASE = "";  // same origin

// ── DOM refs ──────────────────────────────────────────────────
const uploadZone = document.getElementById("upload-zone");
const fileInput = document.getElementById("file-input");
const browseBtn = document.getElementById("browse-btn");
const uploadProgress = document.getElementById("upload-progress");
const progressTitle = document.getElementById("progress-title");
const progressCount = document.getElementById("progress-count");
const progressBar = document.getElementById("progress-bar");
const resultsSection = document.getElementById("results-section");
const resultsGrid = document.getElementById("results-grid");
const clearResultsBtn = document.getElementById("clear-results-btn");
const jobsTbody = document.getElementById("jobs-tbody");
const refreshJobsBtn = document.getElementById("refresh-jobs-btn");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const toastContainer = document.getElementById("toast-container");

// ── Health check on load ──────────────────────────────────────
async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        statusDot.className = "status-dot online";
        statusText.textContent = `Online • ${data.version || "v2.0"}`;
    } catch {
        statusDot.className = "status-dot offline";
        statusText.textContent = "Offline";
    }
}

// ── Toast notifications ───────────────────────────────────────
function showToast(message, type = "info") {
    const icons = { success: "✓", error: "✕", info: "i" };
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || "i"}</span>
        <span>${message}</span>
    `;
    toastContainer.appendChild(toast);
    setTimeout(() => {
        toast.classList.add("removing");
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Drag and drop ─────────────────────────────────────────────
uploadZone.addEventListener("click", () => fileInput.click());
browseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
});

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
        handleFiles(fileInput.files);
        fileInput.value = "";
    }
});

["dragenter", "dragover"].forEach(evt => {
    uploadZone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.add("drag-over");
    });
});

["dragleave", "drop"].forEach(evt => {
    uploadZone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.remove("drag-over");
    });
});

uploadZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFiles(files);
});

// ── File upload ───────────────────────────────────────────────
let parsingInterval;
let timerInterval;

async function handleFiles(fileList) {
    const files = Array.from(fileList).filter(f => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));

    if (files.length === 0) {
        showToast("Please select PDF files only", "error");
        return;
    }

    // Show progress & reset terminal
    uploadProgress.hidden = false;
    const termOut = document.getElementById("terminal-output");
    termOut.innerHTML = `<div>[system] Commencing batch job...</div>`;

    progressTitle.innerHTML = `Processing documents... <span id="timer-display" style="font-family: monospace; font-weight: bold; margin-left:10px;">00:00.000</span>`;
    progressCount.textContent = `0 / ${files.length}`;
    progressBar.style.width = "0%";

    clearInterval(timerInterval);
    const startTime = Date.now();
    timerInterval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const mins = String(Math.floor(elapsed / 60000)).padStart(2, '0');
        const secs = String(Math.floor((elapsed % 60000) / 1000)).padStart(2, '0');
        const millis = String(elapsed % 1000).padStart(3, '0');
        const d = document.getElementById("timer-display");
        if (d) d.textContent = `${mins}:${secs}.${millis}`;
    }, 47);

    const formData = new FormData();
    files.forEach(file => formData.append("files", file));

    try {
        progressBar.style.width = "5%";
        termOut.innerHTML += `<div>[request] Sending payload to origin...</div>`;

        const res = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            body: formData,
        });

        progressBar.style.width = "10%";

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            termOut.innerHTML += `<div style="color:var(--error);">[error] Upload failed</div>`;
            throw new Error(errData.detail || `Upload failed (${res.status})`);
        }

        const data = await res.json();
        const trackingIds = data.jobs.map(j => j.job_id);

        let previouslyRenderedLogs = 0;

        clearInterval(parsingInterval);
        parsingInterval = setInterval(async () => {
            try {
                // Table check
                const jRes = await fetch(`${API_BASE}/jobs`);
                const allJ = await jRes.json();

                let doneCounter = 0;

                trackingIds.forEach(id => {
                    const matched = allJ.find(x => x.id === id);
                    if (matched) {
                        if (["COMPLETED", "FAILED", "REQUIRES_PASSWORD"].includes(matched.status)) {
                            doneCounter++;
                        }
                    }
                });

                progressBar.style.width = `${10 + (doneCounter / trackingIds.length) * 90}%`;
                progressCount.textContent = `${doneCounter} / ${files.length} [ PROCESSING ]`;

                // Fetch terminal logs for the active job
                // Realistically, for multiple files, we'll fetch the first one or merge them. We'll poll trackingIds[0] for simplicity.
                let mergedLogs = [];
                for (let tid of trackingIds) {
                    try {
                        let logRes = await fetch(`${API_BASE}/jobs/${tid}/logs`);
                        let lData = await logRes.json();
                        mergedLogs = mergedLogs.concat(lData.logs.map(l => `[worker-${tid}] ${l}`));
                    } catch (e) { }
                }

                if (mergedLogs.length > previouslyRenderedLogs) {
                    const newLogs = mergedLogs.slice(previouslyRenderedLogs);
                    newLogs.forEach(lg => {
                        termOut.innerHTML += `<div>${escapeHtml(lg)}</div>`;
                    });
                    previouslyRenderedLogs = mergedLogs.length;
                    termOut.scrollTop = termOut.scrollHeight;
                }

                // Refresh table automatically
                allJobs = allJ;
                renderJobsPage();

                if (doneCounter === trackingIds.length) {
                    clearInterval(parsingInterval);
                    clearInterval(timerInterval);

                    progressTitle.innerHTML = `Complete!`;
                    progressCount.textContent = `${doneCounter} / ${files.length}`;
                    progressBar.style.width = "100%";
                    showToast(`${doneCounter} document(s) finished processing`, "success");

                    // Stop relying on result cards implicitly if they conflict
                    if (typeof resultsSection !== "undefined") {
                        resultsSection.hidden = true;
                    }
                    termOut.innerHTML += `<div>[system] Pipeline terminated successfully.</div>`;
                    termOut.scrollTop = termOut.scrollHeight;

                    setTimeout(() => {
                        uploadProgress.hidden = true;
                        progressBar.style.width = "0%";
                    }, 5000);
                }
            } catch (e) {
                // Ignore network slips during poll
            }
        }, 500);

    } catch (err) {
        clearInterval(timerInterval);
        progressBar.style.width = "0%";
        uploadProgress.hidden = true;
        showToast(err.message || "Upload failed", "error");
    }
}



// ── Display Results ───────────────────────────────────────────
function displayResults(results) {
    resultsSection.hidden = false;

    results.forEach((r, i) => {
        const card = document.createElement("div");
        card.className = "result-card";
        card.style.animationDelay = `${i * 0.08}s`;

        const pipelineClass = (r.pipeline || "MANUAL").toLowerCase();
        const confidence = r.confidence ?? 1;
        const confidencePercent = Math.round(confidence * 100);
        const confLevel = confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";

        let debugHtml = "";
        if (r.debug) {
            const debugId = `debug-${Date.now()}-${i}`;
            debugHtml = `
                <button class="debug-toggle" onclick="toggleDebug('${debugId}')">
                    ▸ Debug info
                </button>
                <div class="debug-content" id="${debugId}" hidden>${JSON.stringify(r.debug, null, 2)}</div>
            `;
        }

        let openBtnHtml = "";
        if (r.status === "REQUIRES_PASSWORD") {
            openBtnHtml = `
                <button class="btn btn-open" style="background: var(--error-bg); color: var(--error); border: 1px solid var(--error); cursor: pointer;" onclick="openUnlockModal(${r.job_id || 0})">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                        <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                    </svg>
                    Unlock
                </button>
            `;
        } else if (r.pipeline_url) {
            const btnClass = pipelineClass === "ocr" ? "btn-open-ocr" : "btn-open-llm";
            openBtnHtml = `
                <a href="${r.pipeline_url}" target="_blank" rel="noopener" class="btn btn-open ${btnClass}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                        <polyline points="15,3 21,3 21,9"></polyline>
                        <line x1="10" y1="14" x2="21" y2="3"></line>
                    </svg>
                    Open in ${r.pipeline || "Service"}
                </a>
            `;
        }

        let exportsHtml = "";
        if (r.available_outputs && r.available_outputs.length > 0) {
            const stem = r.file_name.replace(/\.[^/.]+$/, "");
            exportsHtml = `<div style="margin-top:6px; display:flex; gap:4px; font-size:0.75rem;">`;
            r.available_outputs.forEach(ext => {
                exportsHtml += `<a href="/processed/${stem}.${ext.toLowerCase()}" target="_blank" class="badge" style="text-decoration:none; background:var(--bg-card); border:1px solid var(--border-color); color:var(--text-color); cursor:pointer;">↓ Docling ${ext}</a>`;
            });
            exportsHtml += `</div>`;
        }

        let traitsHtml = "";
        if (r.pdf_traits && r.pdf_traits.length > 0) {
            traitsHtml = r.pdf_traits.map(t => `<span class="badge badge-trait">${escapeHtml(t)}</span>`).join("");
        }

        card.innerHTML = `
            <div class="result-info">
                <div class="result-filename">${escapeHtml(r.file_name || "Unknown")}</div>
                <div class="result-meta">
                    <span class="badge badge-type">${r.document_type || "UNKNOWN"}</span>
                    <span class="badge badge-${pipelineClass}">${r.pipeline || "MANUAL"}</span>
                    <span class="badge badge-tier">Tier: ${r.classification_tier || "—"}</span>
                    ${traitsHtml}
                    <div class="confidence-meter">
                        <div class="confidence-bar">
                            <div class="confidence-fill ${confLevel}" style="width: ${confidencePercent}%"></div>
                        </div>
                        <span class="confidence-value">${confidencePercent}%</span>
                    </div>
                </div>
                ${logsHtml}
                    ${debugHtml}
                ${exportsHtml}
                ${r.message ? `<div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">${escapeHtml(r.message)}</div>` : ""}
            </div>
            <div class="result-badges">
                ${openBtnHtml}
                <span class="badge badge-status ${(r.status || "").toLowerCase()}">${r.status || "—"}</span>
                <span style="font-size: 0.7rem; color: var(--text-muted);">Job #${r.job_id || "—"}</span>
            </div>
        `;

        resultsGrid.prepend(card);
    });
}

function toggleDebug(id, btnElement, baseText) {
    const el = document.getElementById(id);
    if (el) {
        el.hidden = !el.hidden;
        if (btnElement && baseText) {
            // Handle dynamically generated action toggles
            btnElement.textContent = el.hidden ? `View ${baseText}` : `Close ${baseText}`;
        } else {
            // Keep legacy behavior safely intact
            const btn = el.previousElementSibling;
            if (btn) btn.textContent = el.hidden ? "▸ Debug info" : "▾ Debug info";
        }
    }
}

// ── Clear results ─────────────────────────────────────────────
clearResultsBtn.addEventListener("click", () => {
    resultsGrid.innerHTML = "";
    resultsSection.hidden = true;
});

// ── Jobs table with pagination ────────────────────────────────
const JOBS_PER_PAGE = 5;
let allJobs = [];
let currentPage = 1;

const paginationEl = document.getElementById("pagination");
const paginationNumbers = document.getElementById("pagination-numbers");
const prevPageBtn = document.getElementById("prev-page-btn");
const nextPageBtn = document.getElementById("next-page-btn");

async function loadJobs() {
    try {
        const res = await fetch(`${API_BASE}/jobs`);
        if (!res.ok) throw new Error("Failed to load jobs");
        allJobs = await res.json();
        currentPage = 1;
        renderJobsPage();
    } catch {
        // silent fail — table stays as-is
    }
}

function renderJobsPage() {
    const totalPages = Math.max(1, Math.ceil(allJobs.length / JOBS_PER_PAGE));

    // Clamp current page
    if (currentPage < 1) currentPage = 1;
    if (currentPage > totalPages) currentPage = totalPages;

    const start = (currentPage - 1) * JOBS_PER_PAGE;
    const pageJobs = allJobs.slice(start, start + JOBS_PER_PAGE);

    if (allJobs.length === 0) {
        jobsTbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="9">No jobs yet — upload documents to get started</td>
            </tr>
        `;
        paginationEl.hidden = true;
        return;
    }

    jobsTbody.innerHTML = pageJobs.map(job => {
        const pipelineClass = (job.route || "MANUAL").toLowerCase();
        const statusClass = (job.status || "").toLowerCase();
        const created = job.created_at ? new Date(job.created_at).toLocaleString() : "—";

        let actionHtml = "—";
        if (job.status === "REQUIRES_PASSWORD") {
            actionHtml = `
                <button class="btn btn-open" style="background: var(--error-bg); color: var(--error); border: 1px solid var(--error); cursor: pointer;" onclick="openUnlockModal(${job.id})">
                    Unlock
                </button>
            `;
        } else if (job.pipeline_url) {
            const btnClass = job.route === "OCR" ? "btn-open-ocr" : "btn-open-llm";
            actionHtml = `
                <a href="${job.pipeline_url}" target="_blank" rel="noopener" class="btn-open ${btnClass}">
                    Open
                </a>
            `;
        }

        let exportsHtml = "";
        if (job.available_outputs && job.available_outputs.length > 0) {
            const stem = job.file_name.replace(/\.[^/.]+$/, "");
            job.available_outputs.forEach(ext => {
                exportsHtml += `<a href="/processed/${stem}.${ext.toLowerCase()}" target="_blank" style="text-decoration:none; padding:4px 8px; background:var(--bg-card); border:1px solid var(--border-color); border-radius:4px; color:var(--text-color); font-size:0.75rem;">${ext}</a>\n`;
            });
        }

        let logsBtn = "", logsContent = "";
        let logsArray = job.debug_info ? job.debug_info.logs : null;
        if (logsArray && Array.isArray(logsArray) && logsArray.length > 0) {
            const logsId = `logs-job-${job.id}`;
            const formattedLogs = logsArray.map(l => `<div style="margin-bottom: 2px;">${escapeHtml(l)}</div>`).join('');
            logsBtn = `
                <button class="debug-toggle" onclick="toggleDebug('${logsId}', this, 'Terminal Logs')" style="font-size: 0.75rem; padding: 4px 8px; background: #1F2937; color: #10B981; border: 1px solid #374151; border-radius: 4px; cursor: pointer;">
                    View Terminal Logs
                </button>
            `;
            logsContent = `
                <div class="debug-content" id="${logsId}" hidden style="margin: 8px; background:#111827; color:#10B981; font-family:monospace; padding:10px; border-radius:6px; max-height: 250px; overflow-y: auto; font-size: 0.7rem; border: 1px solid #374151;">
                    ${formattedLogs}
                </div>
            `;
            delete job.debug_info.logs;
        }

        let debugBtn = "", debugContent = "";
        if (job.debug_info && Object.keys(job.debug_info).length > 0) {
            const debugId = `debug-job-${job.id}`;
            debugBtn = `
                <button class="debug-toggle" onclick="toggleDebug('${debugId}', this, 'JSON Data')" style="font-size: 0.75rem; padding: 4px 8px; background: var(--bg-card); color: var(--text-muted); border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer;">
                    View JSON Data
                </button>
            `;
            debugContent = `
                <div class="debug-content" id="${debugId}" hidden style="margin: 8px; max-height: 200px; overflow: auto; white-space: pre-wrap; font-size: 0.7rem; background: var(--table-header-bg); padding: 8px; border-radius: 4px;">${escapeHtml(JSON.stringify(job.debug_info, null, 2))}</div>
            `;
        }

        // ── Traits column ───────────────────────────────────
        let traitsArray = job.debug_info ? job.debug_info.pdf_traits : null;
        let traitsHtml = '<span style="color:var(--text-muted);">—</span>';
        if (traitsArray && traitsArray.length > 0) {
            traitsHtml = traitsArray.map(t => `<span class="badge badge-trait" style="font-size:0.65rem; padding:2px 6px;">${escapeHtml(t)}</span>`).join('');
        }

        // ── Doc Type column ─────────────────────────────────
        const docType = job.document_type || (job.debug_info ? job.debug_info.final_result : null) || "—";
        const docTypeDisplay = docType === "UNKNOWN" ? "—" : docType.replace(/_/g, ' ');

        // ── Tier column ────────────────────────────────────
        const tierRaw = job.classification_tier || "";
        const tierLabels = { "filename": "Tier 1", "keyword": "Tier 2", "llm": "Tier 3", "none": "—" };
        const tierDisplay = tierLabels[tierRaw] || tierRaw || "—";
        const tierColors = { "Tier 1": "#6366F1", "Tier 2": "#10B981", "Tier 3": "#F59E0B" };
        const tierColor = tierColors[tierDisplay] || "var(--text-muted)";

        return `
            <tr>
                <td>${job.id}</td>
                <td class="file-cell" title="${escapeHtml(job.file_name)}">
                    ${escapeHtml(job.file_name || "—")}
                </td>
                <td><div style="display:flex; gap:4px; flex-wrap:wrap;">${traitsHtml}</div></td>
                <td><span class="badge badge-type">${escapeHtml(docTypeDisplay)}</span></td>
                <td><span class="badge badge-${pipelineClass}">${job.route || "—"}</span></td>
                <td><span style="font-size:0.75rem; font-weight:600; color:${tierColor};">${tierDisplay}</span></td>
                <td><span class="badge badge-status ${statusClass}">${job.status || "—"}</span></td>
                <td>${created}</td>
                <td class="action-cell">
                    <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                        ${actionHtml}
                        ${exportsHtml}
                        ${logsBtn}
                        ${debugBtn}
                    </div>
                </td>
            </tr>
            ${logsContent || debugContent ? `
            <tr>
                <td colspan="9" style="padding: 0; border: none; border-bottom: 1px solid var(--border-color);">
                    ${logsContent}
                    ${debugContent}
                </td>
            </tr>
            ` : ''}
        `;
    }).join("");

    // Update pagination controls
    paginationEl.hidden = totalPages <= 1;
    renderPagination(totalPages, currentPage);
    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages;
}

function renderPagination(totalPages, current) {
    paginationNumbers.innerHTML = "";

    const pages = [];
    const delta = 2; // Number of pages before/after current

    for (let i = 1; i <= totalPages; i++) {
        if (
            i === 1 ||
            i === totalPages ||
            (i >= current - delta && i <= current + delta)
        ) {
            pages.push(i);
        } else if (pages[pages.length - 1] !== "...") {
            pages.push("...");
        }
    }

    pages.forEach(p => {
        if (p === "...") {
            const span = document.createElement("span");
            span.className = "pagination-ellipsis";
            span.textContent = "...";
            paginationNumbers.appendChild(span);
        } else {
            const btn = document.createElement("button");
            btn.className = `page-btn ${p === current ? "active" : ""}`;
            btn.textContent = p;
            btn.onclick = () => {
                if (p !== current) {
                    currentPage = p;
                    renderJobsPage();
                }
            };
            paginationNumbers.appendChild(btn);
        }
    });
}

prevPageBtn.addEventListener("click", () => {
    if (currentPage > 1) {
        currentPage--;
        renderJobsPage();
    }
});

nextPageBtn.addEventListener("click", () => {
    const totalPages = Math.ceil(allJobs.length / JOBS_PER_PAGE);
    if (currentPage < totalPages) {
        currentPage++;
        renderJobsPage();
    }
});

refreshJobsBtn.addEventListener("click", () => {
    loadJobs();
    showToast("Jobs refreshed", "info");
});

// ── Utilities ─────────────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ── Init ──────────────────────────────────────────────────────
checkHealth();
loadJobs();

// ── Periodically check health ────────────────────────────────
setInterval(checkHealth, 30000);

// ── Password Modal ────────────────────────────────────────────
const passwordModal = document.getElementById("password-modal");
const passwordForm = document.getElementById("password-form");
const passwordInput = document.getElementById("unlock-password");
const unlockJobId = document.getElementById("unlock-job-id");
const cancelUnlockBtn = document.getElementById("cancel-unlock-btn");
const submitUnlockBtn = document.getElementById("submit-unlock-btn");

function openUnlockModal(jobId) {
    if (!jobId) return;
    unlockJobId.value = jobId;
    passwordInput.value = '';
    passwordModal.showModal();
}

cancelUnlockBtn.addEventListener("click", () => {
    passwordModal.close();
});

passwordForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const jobId = unlockJobId.value;
    const password = passwordInput.value;
    if (!password) return;

    submitUnlockBtn.disabled = true;
    submitUnlockBtn.textContent = "Unlocking...";

    try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}/unlock`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password })
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || "Failed to unlock document");
        }

        showToast("Document unlocked properly and is being processed", "success");
        passwordModal.close();

        // Refresh the jobs table
        loadJobs();

    } catch (err) {
        showToast(err.message, "error");
    } finally {
        submitUnlockBtn.disabled = false;
        submitUnlockBtn.textContent = "Unlock";
    }
});
