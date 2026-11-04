(function () {
  var root = document.getElementById("metrics");
  if (!root) {
    return;
  }
  var ms = Number(root.getAttribute("data-refresh")) || 5000;
  var noteText = "Updates every 5 seconds. History is kept in memory for at most 60 minutes.";
  var timer = window.setInterval(refresh, ms);

  function refresh() {
    var url = root.getAttribute("data-url") || "/metrics/fragment";
    window.fetch(url, {
      credentials: "same-origin",
      redirect: "manual",
      headers: { Accept: "text/html" }
    }).then(function (res) {
      if (
        res.type === "opaqueredirect" ||
        res.status === 0 ||
        res.status === 301 ||
        res.status === 302 ||
        res.status === 303 ||
        res.status === 307 ||
        res.status === 308
      ) {
        window.clearInterval(timer);
        window.location.assign("/login");
        return null;
      }
      if (!res.ok) {
        throw new Error("refresh failed");
      }
      var type = res.headers.get("content-type") || "";
      if (type.indexOf("text/html") === -1) {
        throw new Error("unexpected response");
      }
      return res.text();
    }).then(function (html) {
      if (!html) {
        return;
      }
      if (html.indexOf('name="password"') !== -1) {
        window.clearInterval(timer);
        window.location.assign("/login");
        return;
      }
      root.innerHTML = html;
      var note = document.getElementById("refresh-note");
      if (note) {
        note.textContent = noteText;
      }
    }).catch(function () {
      var note = document.getElementById("refresh-note");
      if (note) {
        note.textContent = "The latest refresh failed. Showing the last reading.";
      }
    });
  }
})();
