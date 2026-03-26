import re

path = r"D:\projects_all_time\08 Intelligence to choose bw LLM & OCR\00 codes\doc-router\document-router-platform\static\app.js"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

new_func = """// ── File upload ───────────────────────────────────────────────
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
                for(let tid of trackingIds) { 
                    try {
                        let logRes = await fetch(`${API_BASE}/jobs/${tid}/logs`);
                        let lData = await logRes.json();
                        mergedLogs = mergedLogs.concat(lData.logs.map(l => `[worker-${tid}] ${l}`));
                    } catch(e) {}
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
"""

pattern = r"// ── File upload ───────────────────────────────────────────────\s*let parsingInterval;.*?catch \(err\) \{\s*clearInterval\(timerInterval\);\s*progressBar\.style\.width = \"0%\";\s*uploadProgress\.hidden = true;\s*showToast\(err\.message \|\| \"Upload failed\", \"error\"\);\s*\}\s*\}"
result = re.sub(pattern, new_func, content, flags=re.DOTALL)

if content == result:
    print("WARNING: Regex did not match!")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(result)
    print("Patched successfully")
