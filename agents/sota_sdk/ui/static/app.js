/**
 * SOTA Agent Builder — Client-side logic
 *
 * Live preview updates as you type. Downloads ZIP via API.
 */

// ── State ────────────────────────────────────────────────────────────────────

let tags = [];
let activeFile = "agent.py";
let generatedFiles = {};

// ── Elements ─────────────────────────────────────────────────────────────────

const nameEl = document.getElementById("name");
const descEl = document.getElementById("description");
const tagInput = document.getElementById("tag-input");
const tagsContainer = document.getElementById("tags-container");
const versionEl = document.getElementById("version");
const keyEl = document.getElementById("private-key");
const urlEl = document.getElementById("marketplace-url");
const chainEl = document.getElementById("chain");
const ratioEl = document.getElementById("price-ratio");
const minBudgetEl = document.getElementById("min-budget");
const codeOutput = document.getElementById("code-output");
const checkResults = document.getElementById("check-results");

// ── Tags ─────────────────────────────────────────────────────────────────────

function renderTags() {
    // Remove existing tag elements (keep input)
    tagsContainer.querySelectorAll(".tag").forEach(el => el.remove());

    tags.forEach((tag, i) => {
        const span = document.createElement("span");
        span.className = "tag";
        span.innerHTML = `${escapeHtml(tag)} <button onclick="removeTag(${i})">&times;</button>`;
        tagsContainer.insertBefore(span, tagInput);
    });
}

function addTag(value) {
    const cleaned = value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "_");
    if (cleaned && !tags.includes(cleaned)) {
        tags.push(cleaned);
        renderTags();
        updatePreview();
    }
}

function removeTag(index) {
    tags.splice(index, 1);
    renderTags();
    updatePreview();
}

tagInput.addEventListener("keydown", e => {
    if (e.key === "Enter") {
        e.preventDefault();
        addTag(tagInput.value);
        tagInput.value = "";
    }
    if (e.key === "Backspace" && !tagInput.value && tags.length) {
        tags.pop();
        renderTags();
        updatePreview();
    }
});

// ── Code Generation (client-side for instant preview) ────────────────────────

function toClassName(name) {
    return name.split(/[-_ ]+/).map(p => p.charAt(0).toUpperCase() + p.slice(1)).join("") + "Agent";
}

function generateAgentPy() {
    const name = nameEl.value || "my-agent";
    const desc = descEl.value || "TODO: describe what this agent does";
    const cls = toClassName(name);
    const tagsStr = (tags.length ? tags : ["my_capability"]).map(t => `"${t}"`).join(", ");
    const ratio = parseFloat(ratioEl.value) || 0.80;
    const minBdg = parseFloat(minBudgetEl.value) || 0.50;

    const needsCustomBid = ratio !== 0.80 || minBdg !== 0.50;
    const importLine = needsCustomBid
        ? "from sota_sdk import SOTAAgent, Job, DefaultBidStrategy"
        : "from sota_sdk import SOTAAgent, Job";
    const bidLine = needsCustomBid
        ? `    bid_strategy = DefaultBidStrategy(price_ratio=${ratio}, min_budget_usdc=${minBdg})\n`
        : "";

    return `"""\n${name} -- SOTA Marketplace Agent\n\nCreated with: sota init ${name}\nRun with:     sota run\n"""\n${importLine}\n\n\nclass ${cls}(SOTAAgent):\n    name = "${name}"\n    description = "${desc}"\n    tags = [${tagsStr}]\n${bidLine}\n    def setup(self):\n        """Called once at startup. Initialize API clients, load models, etc."""\n        pass\n\n    async def execute(self, job: Job) -> dict:\n        """Execute a job and return results."""\n        # TODO: implement your agent logic here\n        return {"success": True, "result": f"Processed: {job.description}"}\n\n\nif __name__ == "__main__":\n    ${cls}.run()\n`;
}

function generateEnv() {
    const key = keyEl.value || "           # 64 hex chars";
    const url = urlEl.value || "ws://localhost:3002/ws/agent";
    const clusterMap = { "solana-devnet": "devnet", "solana-mainnet": "mainnet-beta" };
    const cluster = clusterMap[chainEl.value] || "devnet";

    return `# === SOTA Agent Environment ===\nSOTA_AGENT_PRIVATE_KEY=${key}\nSOTA_MARKETPLACE_URL=${url}\nSOLANA_CLUSTER=${cluster}\n`;
}

function generateDockerfile() {
    return `FROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nEXPOSE 8000\nHEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"\nCMD ["python", "agent.py"]\n`;
}

function generateRequirements() {
    return "sota-sdk>=0.3.0\n";
}

function updatePreview() {
    generatedFiles = {
        "agent.py": generateAgentPy(),
        ".env": generateEnv(),
        "Dockerfile": generateDockerfile(),
        "requirements.txt": generateRequirements(),
    };
    codeOutput.textContent = generatedFiles[activeFile] || "";
}

// ── File Tabs ────────────────────────────────────────────────────────────────

document.getElementById("file-tabs").addEventListener("click", e => {
    if (e.target.classList.contains("file-tab")) {
        document.querySelectorAll(".file-tab").forEach(t => t.classList.remove("active"));
        e.target.classList.add("active");
        activeFile = e.target.dataset.file;
        updatePreview();
    }
});

// ── API Calls ────────────────────────────────────────────────────────────────

function getConfig() {
    return {
        name: nameEl.value || "my-agent",
        description: descEl.value || "",
        tags: tags.length ? tags : ["my_capability"],
        version: versionEl.value || "1.0.0",
        private_key: keyEl.value || "",
        marketplace_url: urlEl.value || "ws://localhost:3002/ws/agent",
        chain: chainEl.value || "solana-devnet",
        price_ratio: parseFloat(ratioEl.value) || 0.80,
        min_budget: parseFloat(minBudgetEl.value) || 0.50,
    };
}

async function downloadZip() {
    try {
        const resp = await fetch("/api/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(getConfig()),
        });
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${nameEl.value || "my-agent"}.zip`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (err) {
        checkResults.innerHTML = `<div class="check-results error">Download failed: ${escapeHtml(err.message)}</div>`;
    }
}

async function runCheck() {
    try {
        const config = getConfig();
        const resp = await fetch("/api/check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: config.name,
                tags: config.tags,
                marketplace_url: config.marketplace_url,
                private_key: config.private_key,
            }),
        });
        const data = await resp.json();

        let html = "";
        if (data.ok) {
            html = `<div class="check-results success">All checks passed!</div>`;
        }
        if (data.warnings && data.warnings.length) {
            html += `<div class="check-results warning"><strong>Warnings:</strong><ul>${data.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join("")}</ul></div>`;
        }
        if (data.errors && data.errors.length) {
            html += `<div class="check-results error"><strong>Errors:</strong><ul>${data.errors.map(e => `<li>${escapeHtml(e)}</li>`).join("")}</ul></div>`;
        }
        checkResults.innerHTML = html;
    } catch (err) {
        checkResults.innerHTML = `<div class="check-results error">Check failed: ${escapeHtml(err.message)}</div>`;
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ── Live Preview (debounced) ─────────────────────────────────────────────────

let debounceTimer;
function debouncedPreview() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(updatePreview, 150);
}

[nameEl, descEl, versionEl, keyEl, urlEl, ratioEl, minBudgetEl].forEach(el => {
    el.addEventListener("input", debouncedPreview);
});
chainEl.addEventListener("change", debouncedPreview);

// ── Initialize ──────────────────────────────────────────────────────────────

updatePreview();
