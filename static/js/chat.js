const socket = io();
const box = document.getElementById("chatBox");
const input = document.getElementById("messageInput");
const send = document.getElementById("sendBtn");
socket.emit("join", { other_id: window.chatOtherId });
box.scrollTop = box.scrollHeight;

function addMessage(text, isMe = false) {
  const el = document.createElement("div");
  el.className = "msg" + (isMe ? " me" : "");
  el.textContent = text;
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
}

send.onclick = () => {
  const txt = input.value.trim();
  if (!txt) return;
  socket.emit("send_message", { receiver: window.chatOtherId, message: txt });
  input.value = "";
};

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") send.click();
});

socket.on("new_message", (data) => {
  const isMe = String(data.sender) !== String(window.chatOtherId);
  addMessage(data.message, isMe);
});
