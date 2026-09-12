# Merchant onboarding API handoff

All routes are server-authoritative and are intended to sit behind the
authenticated merchant router. The route owner derives `merchant_id` and
`user_id` from authentication in production; the development adapter exposes
them as route/body values for clarity.

## State and profile

`GET /api/merchants/{merchantId}/onboarding` returns the saved step, completed
steps, draft/submitted state, last-save time, incomplete requirements, uploads,
policy status, and current membership policy.

`PUT /api/merchants/{merchantId}/onboarding/profile`

```json
{"profile":{"business_name":"Harbor Tech","registration":"ABN 51...","contact":"Ada"},"current_step":"files"}
```

## Uploads and catalogue readiness

`POST /api/merchants/{merchantId}/onboarding/uploads` is multipart with
`document_type` (`business_document`, `shipping`, `returns`, `privacy`,
`terms`) and `file`. It returns `file_id`, filename, type, `accepted` or
`rejected` state, and a validation message.

`POST /api/merchants/{merchantId}/onboarding/catalogue/import` is multipart
with `file` (`.csv` or `.xlsx`). Its response includes counts, recognised field
mapping, missing required fields, row errors, and destination steps.

```json
{"total_imported_products":3,"valid_products":2,"rejected_products":1,"mapped_fields":{"sku":"SKU","name":"Product","price":"Price"},"missing_required_fields":[],"row_errors":[{"row":4,"fields":["price"],"message":"Required value missing.","destination_step":"catalogue"}],"issue_destination_step":"catalogue"}
```

## Consent and submission

`GET /api/membership-policy/current` returns `{policy_id, version,
content_reference}`. `POST /api/merchants/{merchantId}/onboarding/membership-consent`
accepts `{user_id, policy_id, version}` and returns the immutable acceptance
record. A stale version receives HTTP 409.

`POST /api/merchants/{merchantId}/onboarding/submit` accepts `{user_id}`. It
returns either `{accepted:true,status:"submitted",...}` or
`{accepted:false,status:"blocked",incomplete_requirements:[...]}`. Submission
records do not publish catalogue data.
