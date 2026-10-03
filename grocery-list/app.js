const CHECKED_KEY = "groceryCheckedV1";
const CACHE_KEY = "groceryItemsCacheV1";

let items = [];
let checked = {};
let showCompleted = false;

function readJsonStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (error) {
    console.error(`Failed to read ${key}:`, error);
    return fallback;
  }
}

function writeJsonStorage(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.error(`Failed to save ${key}:`, error);
  }
}

function isValidItem(item) {
  return item &&
    typeof item.id === "string" &&
    typeof item.category === "string" &&
    typeof item.text === "string";
}

async function loadItems() {
  checked = readJsonStorage(CHECKED_KEY, {});
  try {
    const response = await fetch("./items.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`items.json returned HTTP ${response.status}`);
    }
    const data = await response.json();
    if (!Array.isArray(data) || !data.every(isValidItem)) {
      throw new Error("items.json has an invalid schema");
    }
    items = data;
    writeJsonStorage(CACHE_KEY, data);
  } catch (error) {
    console.error("Could not load current grocery list:", error);
    items = readJsonStorage(CACHE_KEY, []);
    document.getElementById("error").hidden = items.length > 0;
  }
  render();
}

function setChecked(id, value) {
  try {
    checked[id] = value;
    writeJsonStorage(CHECKED_KEY, checked);
    render();
  } catch (error) {
    console.error("Could not update checked state:", error);
  }
}

function makeItemRow(item, done) {
  const row = document.createElement("div");
  row.className = "item";

  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = done;
  box.id = `item-${item.id}`;
  box.addEventListener("change", () => setChecked(item.id, box.checked));

  const label = document.createElement("label");
  label.htmlFor = box.id;
  label.textContent = item.text;

  row.append(box, label);
  return row;
}

function renderGrouped(target, list, completed = false) {
  target.innerHTML = "";
  const categories = [...new Set(list.map(item => item.category))];
  for (const category of categories) {
    const section = document.createElement("section");
    section.className = completed ? "section completed" : "section";

    const heading = document.createElement("h2");
    heading.textContent = category;
    section.appendChild(heading);

    list
      .filter(item => item.category === category)
      .forEach(item => section.appendChild(makeItemRow(item, completed)));

    target.appendChild(section);
  }
}

function render() {
  try {
    const active = items.filter(item => !checked[item.id]);
    const done = items.filter(item => checked[item.id]);

    document.getElementById("status").textContent =
      `${active.length} item${active.length === 1 ? "" : "s"} left`;

    const activeRoot = document.getElementById("active");
    if (active.length) {
      renderGrouped(activeRoot, active, false);
    } else {
      activeRoot.innerHTML = '<div class="empty">Everything on the list is checked off.</div>';
    }

    const toggle = document.getElementById("toggleCompleted");
    toggle.textContent = showCompleted
      ? "Hide checked"
      : `Show checked (${done.length})`;
    toggle.disabled = done.length === 0;

    const completedRoot = document.getElementById("completed");
    completedRoot.hidden = !showCompleted || done.length === 0;
    if (showCompleted && done.length) {
      renderGrouped(completedRoot, done, true);
    }
  } catch (error) {
    console.error("Could not render grocery list:", error);
    document.getElementById("error").hidden = false;
  }
}

document.getElementById("toggleCompleted").addEventListener("click", () => {
  showCompleted = !showCompleted;
  render();
});

document.getElementById("uncheckAll").addEventListener("click", () => {
  try {
    checked = {};
    writeJsonStorage(CHECKED_KEY, checked);
    render();
  } catch (error) {
    console.error("Could not reset checked items:", error);
  }
});

loadItems().catch(error => {
  console.error("Unexpected grocery list startup error:", error);
  document.getElementById("error").hidden = false;
});
