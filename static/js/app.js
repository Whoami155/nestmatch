let mode = "roommate";
let cards = [];
let index = 0;
let history = { roommate: [], property: [] };
let pointerDown = false;
const cardWrap = document.getElementById("cardWrap");
const likeBtn = document.getElementById("likeBtn");
const dislikeBtn = document.getElementById("dislikeBtn");
const popup = document.getElementById("matchPopup");
const meta = document.getElementById("deckMeta");
const likesCount = document.getElementById("likesCount");
const skipsCount = document.getElementById("skipsCount");
const superLikesCount = document.getElementById("superLikesCount");
const remainingCount = document.getElementById("remainingCount");
const progressBar = document.getElementById("progressBar");
const superLikeBtn = document.getElementById("superLikeBtn");
const undoBtn = document.getElementById("undoBtn");
const modeSlider = document.getElementById("modeSlider");

function inrRange(minVal, maxVal) {
  const min = Number(minVal || 0);
  const max = Number(maxVal || 0);
  if (!min && !max) return "₹10k-₹15k";
  if (min && max) return `₹${Math.round(min / 1000)}k-₹${Math.round(max / 1000)}k`;
  return `₹${Math.round((min || max) / 1000)}k`;
}

function pctBar(label, value) {
  const safe = Number(value || 0);
  return `<div class="compat-item" title="${label}: ${safe}%"><span>${label}</span><div class="compat-track"><div class="compat-fill" style="width:${safe}%"></div></div><strong>${safe}%</strong></div>`;
}

function cardHtml(item) {
  if (mode === "roommate") {
    const breakdown = item.compatibility_breakdown || {};
    const interests = (item.interests || ["Music", "Gym", "Coding"]).slice(0, 4);
    return `
      <article class="card">
        ${item.profile_picture ? `<img class="roommate-avatar" src="${item.profile_picture}" alt="${item.name || "User"}">` : ""}
        <div class="hero-line">
          <h2 class="hero-title">${item.name || "User"}</h2>
          <span class="compat-pill">${item.compatibility_score || 0}% • ${item.compatibility_label || "Low"}</span>
        </div>
        <div class="subline">${item.occupation || "Lifestyle not shared"} • 📍 ${item.preferred_location || "Flexible location"} • ${item.distance_km || 0} km away</div>
        <div class="smart-tag">${item.smart_tag || "✨ Promising compatibility blend"}</div>
        <div class="detail-grid">
          <span class="detail-chip">🛏 ${item.sleep_schedule || "Flexible sleep"}</span>
          <span class="detail-chip">🧹 Cleanliness ${item.cleanliness || "-"}/5</span>
          <span class="detail-chip">🍺 ${item.smoke_drink || "No habit preference"}</span>
          <span class="detail-chip">💸 ${inrRange(item.budget_min, item.budget_max)}</span>
        </div>
        <p class="bio">${item.bio || "This user has not added a bio yet."}</p>
        <div class="compat-breakdown">
          ${pctBar("Budget", breakdown.budget || 0)}
          ${pctBar("Lifestyle", breakdown.lifestyle || 0)}
          ${pctBar("Location", breakdown.location || 0)}
        </div>
        <div class="badge-row">
          ${interests.map((x) => `<span class="tag">🎵 ${x}</span>`).join("")}
        </div>
        <div class="roommate-actions">
          <a class="ghost-link" href="/roommate/${item.id}">View Profile</a>
          <a class="ghost-link" href="mailto:${item.email || ""}?subject=NestMatch%20Connection">Contact</a>
          ${
            item.can_message
              ? `<a class="ghost-link" href="/chat/${item.id}">Message</a>`
              : `<button class="ghost-link" type="button" data-need-match="1">Message</button>`
          }
        </div>
      </article>
    `;
  }
  const image = item.images && item.images.length ? `<img class="property-image" src="${item.images[0]}" alt="${item.title || "Property"}">` : `<div class="property-image"></div>`;
  return `
    <article class="card">
      ${image}
      <div class="hero-line">
        <h2 class="hero-title">${item.title || "Property"}</h2>
        <span class="tag">${item.property_type || "Rent"}</span>
      </div>
      <div class="subline">📍 ${item.location || "Location unavailable"} • 2.8 km away</div>
      <div class="map-preview">🗺 Approx map preview: ${(item.location || "Locality").split(",")[0]}</div>
      <div class="price-line">₹ ${Number(item.price || 0).toLocaleString("en-IN")}</div>
      <p class="bio">${item.description || "No description available for this listing yet."}</p>
    </article>
  `;
}

function nextCardPreview(item) {
  if (!item) return "";
  return `<article class="card card-next"><h3>${mode === "roommate" ? (item.name || "Upcoming match") : (item.title || "Upcoming listing")}</h3><p>${mode === "roommate" ? (item.preferred_location || "Flexible location") : (item.location || "Location unavailable")}</p></article>`;
}

function refreshStats() {
  const likes = history[mode].filter((x) => x.action === "like").length;
  const skips = history[mode].filter((x) => x.action === "dislike").length;
  const supers = history[mode].filter((x) => x.action === "superlike").length;
  const remaining = Math.max(cards.length - index, 0);
  likesCount.textContent = String(likes);
  skipsCount.textContent = String(skips);
  superLikesCount.textContent = String(supers);
  remainingCount.textContent = String(remaining);
  const progress = cards.length ? ((index / cards.length) * 100).toFixed(1) : 0;
  progressBar.style.width = `${progress}%`;
  meta.textContent = `${mode === "roommate" ? "Roommate" : "Property"} deck • ${index}/${cards.length} reviewed`;
}

function render() {
  if (index >= cards.length) {
    cardWrap.innerHTML = `<article class="card"><h2 class="hero-title">No more cards for now</h2><p class="bio">You are all caught up. Switch mode or check back later for fresh recommendations.</p></article>`;
    refreshStats();
    return;
  }
  cardWrap.innerHTML = `${nextCardPreview(cards[index + 1])}${cardHtml(cards[index])}`;
  attachCardMotion();
  refreshStats();
}

function attachCardMotion() {
  const card = cardWrap.querySelector(".card:not(.card-next)");
  if (!card) return;
  card.addEventListener("pointermove", (e) => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const rx = ((y / rect.height) - 0.5) * -6;
    const ry = ((x / rect.width) - 0.5) * 8;
    if (!pointerDown) card.style.transform = `rotateX(${rx}deg) rotateY(${ry}deg)`;
  });
  card.addEventListener("pointerleave", () => {
    if (!pointerDown) card.style.transform = "";
  });
}

async function loadCards() {
  const url = mode === "roommate" ? "/api/discover/roommates" : "/api/discover/properties";
  cards = await fetch(url).then((r) => r.json());
  index = 0;
  meta.textContent = "Deck loaded";
  render();
}

async function swipe(action) {
  if (index >= cards.length) return;
  const item = cards[index];
  const endpoint = mode === "roommate" ? "/api/swipe/roommate" : "/api/swipe/property";
  const body = mode === "roommate" ? { target_user_id: item.id, action } : { property_id: item.id, action };
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());
  history[mode].push({ id: item.id, action, at: new Date().toISOString() });
  if (res.match_created) {
    popup.classList.remove("hidden");
    setTimeout(() => popup.classList.add("hidden"), 1800);
  }
  const activeCard = cardWrap.querySelector(".card:not(.card-next)");
  if (activeCard) {
    if (action === "like" || action === "superlike") {
      activeCard.classList.add("swipe-right");
      likeBtn.classList.add("pulse-like");
      setTimeout(() => likeBtn.classList.remove("pulse-like"), 260);
    } else {
      activeCard.classList.add("swipe-left");
    }
    await new Promise((resolve) => setTimeout(resolve, 120));
  }
  index += 1;
  render();
}

async function undoSwipe() {
  if (!history[mode].length) return;
  const endpoint = "/api/swipe/undo";
  await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: mode }),
  });
  const previous = history[mode].pop();
  const backIndex = cards.findIndex((x) => String(x.id) === String(previous.id));
  if (backIndex >= 0) {
    index = backIndex;
    render();
  }
}

function updateModeUI() {
  if (!modeSlider) return;
  modeSlider.style.transform = mode === "roommate" ? "translateX(0%)" : "translateX(100%)";
}

document.getElementById("roommateMode").onclick = () => {
  mode = "roommate";
  document.getElementById("roommateMode").classList.add("active");
  document.getElementById("propertyMode").classList.remove("active");
  likeBtn.textContent = "❤️";
  superLikeBtn.classList.remove("hidden");
  dislikeBtn.classList.remove("hidden");
  updateModeUI();
  loadCards();
};
document.getElementById("propertyMode").onclick = () => {
  mode = "property";
  document.getElementById("propertyMode").classList.add("active");
  document.getElementById("roommateMode").classList.remove("active");
  likeBtn.textContent = "❤️";
  superLikeBtn.classList.remove("hidden");
  dislikeBtn.classList.remove("hidden");
  updateModeUI();
  loadCards();
};

likeBtn.onclick = () => swipe("like");
dislikeBtn.onclick = () => swipe("dislike");
superLikeBtn.onclick = () => swipe("superlike");
undoBtn.onclick = undoSwipe;
let dragStart = null;
cardWrap.addEventListener("pointerdown", (e) => {
  pointerDown = true;
  dragStart = e.clientX;
});
cardWrap.addEventListener("pointerup", (e) => {
  if (dragStart === null) return;
  const dx = e.clientX - dragStart;
  if (dx > 90) swipe("like");
  if (dx < -90) swipe("dislike");
  dragStart = null;
  pointerDown = false;
});
cardWrap.addEventListener("click", (e) => {
  const el = e.target.closest("[data-need-match]");
  if (!el) return;
  e.preventDefault();
  popup.textContent = "Like each other first to unlock chat";
  popup.classList.remove("hidden");
  setTimeout(() => {
    popup.classList.add("hidden");
    popup.textContent = "New Match Unlocked";
  }, 1800);
});

loadCards();
updateModeUI();
