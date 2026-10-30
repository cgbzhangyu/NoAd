/* NoAd SMZDM splash response filter. */

try {
  const payload = JSON.parse($response.body);
  if (payload && typeof payload === "object") {
    delete payload.data;
  }
  $done({ body: JSON.stringify(payload) });
} catch (_) {
  $done({});
}
