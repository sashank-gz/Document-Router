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
async function handleFiles(fileList) {
    const files = Array.from(fileList).filter(f => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));

    if (files.length === 0) {
        showToast("Please select PDF files only", "error");
        return;
    }

    // Show progress
    uploadProgress.hidden = false;
    progressTitle.textContent = "Processing documents...";
    progressCount.textContent = `0 / ${files.length}`;
    progressBar.style.width = "0%";

    const formData = new FormData();
    files.forEach(file => formData.append("files", file));

    try {
        // Animate progress smoothly
        progressBar.style.width = "30%";

        const res = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            body: formData,
        });

        progressBar.style.width = "80%";

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `Upload failed (${res.status})`);
        }

        const data = await res.json();
        progressBar.style.width = "100%";
        progressCount.textContent = `${data.count} / ${files.length}`;
        progressTitle.textContent = "Complete!";

        showToast(`${data.count} document(s) classified successfully`, "success");
        displayResults(data.results);
        loadJobs();

        // Hide progress after a moment
        setTimeout(() => {
            uploadProgress.hidden = true;
            progressBar.style.width = "0%";
        }, 2000);

    } catch (err) {
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
        if (r.pipeline_url) {
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

        card.innerHTML = `
            <div class="result-info">
                <div class="result-filename">${escapeHtml(r.file_name || "Unknown")}</div>
                <div class="result-meta">
                    <span class="badge badge-type">${r.document_type || "UNKNOWN"}</span>
                    <span class="badge badge-${pipelineClass}">${r.pipeline || "MANUAL"}</span>
                    <span class="badge badge-tier">Tier: ${r.classification_tier || "—"}</span>
                    <div class="confidence-meter">
                        <div class="confidence-bar">
                            <div class="confidence-fill ${confLevel}" style="width: ${confidencePercent}%"></div>
                        </div>
                        <span class="confidence-value">${confidencePercent}%</span>
                    </div>
                </div>
                ${debugHtml}
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

function toggleDebug(id) {
    const el = document.getElementById(id);
    if (el) {
        el.hidden = !el.hidden;
        const btn = el.previousElementSibling;
        if (btn) btn.textContent = el.hidden ? "▸ Debug info" : "▾ Debug info";
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
                <td colspan="6">No jobs yet — upload documents to get started</td>
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
        if (job.pipeline_url) {
            const btnClass = job.route === "OCR" ? "btn-open-ocr" : "btn-open-llm";
            actionHtml = `
                <a href="${job.pipeline_url}" target="_blank" rel="noopener" class="btn-open ${btnClass}">
                    Open
                </a>
            `;
        }

        return `
            <tr>
                <td>${job.id}</td>
                <td class="file-cell" title="${escapeHtml(job.file_name)}">${escapeHtml(job.file_name || "—")}</td>
                <td><span class="badge badge-type">${job.route || "—"}</span></td>
                <td><span class="badge badge-${pipelineClass}">${job.route || "—"}</span></td>
                <td><span class="badge badge-status ${statusClass}">${job.status || "—"}</span></td>
                <td>${created}</td>
                <td class="action-cell">${actionHtml}</td>
            </tr>
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

// Periodically check health
setInterval(checkHealth, 30000);

