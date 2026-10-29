# Security Policy

NoAd never needs user cookies, tokens, account identifiers, full request URLs,
request/response bodies, HAR archives, CA private keys or payment information.

Please report rule poisoning, unsafe MITM scope, external script injection or
credential exposure through GitHub private vulnerability reporting. For normal
false positives, use the issue template and include only sanitized host/path
metadata.

Stable modules must not contain MITM, scripts, URL rewrites, DIRECT/PROXY rules,
DNS changes or certificate material.

