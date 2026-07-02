const Network = (() => {
  function getInitData() {
    return (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) || "";
  }

  async function _post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": getInitData(),
      },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async function auth() {
    return _post("/api/auth", { initData: getInitData() });
  }

  async function finishRun({ waveReached, durationSeconds, killsByType }) {
    return _post("/api/run/finish", {
      initData: getInitData(),
      wave_reached: waveReached,
      duration_seconds: durationSeconds,
      kills_by_type: killsByType,
    });
  }

  return { auth, finishRun, getInitData };
})();