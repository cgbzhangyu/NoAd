/*
 * NoAd Bilibili splash response filter.
 *
 * The Shadowrocket module limits execution to app.bilibili.com/x/v2/splash/
 * responses. This script performs no logging, persistence, notifications or
 * network requests. Parse failures and unexpected response shapes are passed
 * through unchanged.
 */

(() => {
  try {
    if (
      typeof $response === "undefined" ||
      typeof $response.body !== "string" ||
      $response.body.length === 0
    ) {
      $done({});
      return;
    }

    const payload = JSON.parse($response.body);
    if (
      !payload ||
      payload.code !== 0 ||
      !payload.data ||
      typeof payload.data !== "object" ||
      Array.isArray(payload.data)
    ) {
      $done({});
      return;
    }

    payload.data.max_time = 0;
    payload.data.keep_ids = [];
    payload.data.list = [];
    payload.data.show = [];

    $done({ body: JSON.stringify(payload) });
  } catch (_) {
    $done({});
  }
})();
