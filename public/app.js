const form = document.getElementById("generate-form");
const input = document.getElementById("job-title");
const submitBtn = document.getElementById("submit-btn");
const errorEl = document.getElementById("error");
const loadingEl = document.getElementById("loading");
const resultsEl = document.getElementById("results");
const resultsHeading = document.getElementById("results-heading");
const questionsList = document.getElementById("questions-list");

function setError(message) {
  if (message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  } else {
    errorEl.textContent = "";
    errorEl.hidden = true;
  }
}

function setLoading(isLoading) {
  loadingEl.hidden = !isLoading;
  submitBtn.disabled = isLoading;
  submitBtn.textContent = isLoading ? "Generating…" : "Generate";
}

function renderResults(jobTitle, questions) {
  resultsHeading.textContent = `Interview questions for ${jobTitle}`;
  questionsList.innerHTML = "";
  for (const q of questions) {
    const li = document.createElement("li");
    li.textContent = q;
    questionsList.appendChild(li);
  }
  resultsEl.hidden = false;
}

async function generate(jobTitle) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  let res;
  try {
    res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_title: jobTitle }),
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (data && data.message) message = data.message;
      else if (data && data.detail) message = data.detail;
    } catch {
      /* ignore JSON parse errors on error responses */
    }
    throw new Error(message);
  }

  return res.json();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const jobTitle = input.value.trim();
  if (!jobTitle) {
    setError("Please enter a job title.");
    return;
  }

  setError(null);
  resultsEl.hidden = true;
  setLoading(true);

  try {
    const data = await generate(jobTitle);
    renderResults(data.job_title, data.questions);
  } catch (err) {
    setError(err.message || "Something went wrong. Please try again.");
  } finally {
    setLoading(false);
  }
});
