# API error codes

Every error response has the same shape (F-160):

```json
{"code": "STALE_BOOKING", "detail": "Someone changed this booking since you opened it.", "...": "extra keys some codes add"}
```

- `code` is stable; key your handling on it. `detail` is English for people.
- A field error (`INVALID`) also has `fields`: `{"field": ["what is wrong"]}` (the old top-level field keys stay for older clients).
- Refused answers (`INVALID_ANSWERS`) carry `errors` `{key: code}` and `messages` `{key: words}`.
- A stale edit (`STALE_BOOKING`, `STALE_INSPECTION`) carries `changed_by`, `changed_at`, `changed_keys`, `row_version`.

Alert codes on a booking (`alerts[].code`, not errors): `TYPE_CHANGE_REJECTED`, `CONFLICT_TWO_EXPERTS`,
`RELEASED_DRAFT_ARRIVED`, `LATE_WORK` (offline work on a form switched off, a form version replaced after
the start, or an app version too old since), `FORM_VERSION_REFUSED`.

This table is made from the code (`apps/platform/error_codes.py`); a test fails when it is out of date.
Regenerate: `uv run python -c "from apps.platform.error_codes import table; print(table())"`.

<!-- table -->
| Code | HTTP | Meaning |
|---|---|---|
| `ACTION_NOT_ALLOWED` | 403 | This key may not …. Ask an Admin to allow it. |
| `ADMIN_ONLY` | 403 | Only an Admin can manage Admin users. |
| `ADMIN_ROLE_LOCKED` | 400 | The Admin role always has full access. |
| `ADMIN_USE_WEB` | 403 | The app is for Ops and experts. Admins use the web. |
| `ALREADY_LINKED` | 409 | This item is already linked to the library. |
| `ALREADY_STARTED` | 409 | The expert has started; force-release the booking first. |
| `ALREADY_SUBMITTED` | 409 | Already submitted; Ops can edit it. |
| `APP_TOO_OLD` | 426 | Update the app to start new leads. |
| `ARCHIVED` | 409 | This library item is archived. |
| `AUTHENTICATION_FAILED` | 401 | The token or key is not valid. |
| `BAD_ORIGIN` | 403 | Sign in from the Vayu page itself. |
| `BOOKING_CLOSED` | 409 | A … … takes no new files. |
| `BUNDLE_TOO_NEW` | 400 | This bundle comes from a newer version of Vayu; upgrade this server first. |
| `CANNOT_REGENERATE` | 409 | … |
| `CONFIRM_REQUIRED` | 400 | Publishing cannot be undone: confirm it. |
| `CONFLICT_OPEN` | 409 | Choose which inspection counts first. |
| `DELETE_NOT_ALLOWED` | 403 | Only an Admin can delete a booking that has been assigned or worked on. Cancel it instead. |
| `DEVICE_HAS_UNSYNCED_DATA` | 409 | Your other phone still has work that hasn't been sent. Open the app there and let it sync, or ask an Admin to sign that phone out. |
| `DEVICE_REVOKED` | 401 | This device was signed out. |
| `DRAFT_EXISTS` | 409 | This form already has a draft; publish or discard it first. |
| `DUPLICATE_BOOKING_ID` | 400 | Booking ID '…' is already used. |
| `DUPLICATE_KEY` | 400 | A library … with key '…' already exists. |
| `FIELD_ACCESS` | 403 | You cannot change these fields at this stage. |
| `FIELD_NOT_EDITABLE` | 400 | Only an Admin can change that. You can change your theme here. |
| `FILE_REMOVAL_NOT_ALLOWED` | 403 | Files cannot be removed. Replace them on the Media tab instead. |
| `FIRST_DRAFT` | 409 | This form has never been published: there is nothing to go back to. Publish it, or ask an Admin to deactivate the form. |
| `FORBIDDEN` | 403 | Choosing the expert needs the assign permission. |
| `FORM_VERSION_OLD` | 409 | This lead was filled on a form that had already been replaced. Ops have been told. |
| `IMAGE_TOO_LARGE` | 413 | The picture must be 5 MB or smaller. |
| `IMPORT_CONFLICTS` | 400 | This bundle conflicts with what is already here. |
| `INCOMPLETE_UPLOAD` | 400 | Some parts are missing or do not match. |
| `INVALID` | 400 | A field is invalid; `fields` says which. |
| `INVALID_ACCESS` | 400 | … |
| `INVALID_ACTIONS` | 400 | allowed_actions is a list of: …. |
| `INVALID_ANSWERS` | 400 | Some answers are invalid. |
| `INVALID_BODY` | 400 | The body is JSON. |
| `INVALID_BOOKING` | 400 | Pick a submitted booking inspected with this form. |
| `INVALID_BUNDLE` | 400 | A picture in the bundle is damaged. |
| `INVALID_CHECK` | 400 | A check needs a message. |
| `INVALID_CONFIG` | 400 | Unknown field type '…'. |
| `INVALID_CONTENT_TYPE` | 400 | … is not allowed for a …. |
| `INVALID_COUNTS` | 400 | drafts and files must be whole numbers, 0 or more. |
| `INVALID_CREDENTIALS` | 401 | Invalid username or password. |
| `INVALID_DEFINITION` | 400 | A field definition needs key, label and type, and only these properties: …. |
| `INVALID_EVENT` | 400 | A booking form integration can only use booking events. |
| `INVALID_EXPERT` | 400 | Choose an active expert. |
| `INVALID_FIELDS` | 400 | fields must be a list of field keys. |
| `INVALID_FLAG` | 400 | Say which flag: late or quick. |
| `INVALID_FORM` | 400 | Choose a booking or inspection form. |
| `INVALID_HEADERS` | 400 | Headers are a list of up to …. |
| `INVALID_IDS` | 400 | Send the ids to mark read, or all: true. |
| `INVALID_IMAGE` | 400 | Choose a picture to upload. |
| `INVALID_INPUT` | 400 | … |
| `INVALID_INSPECTION` | 400 | Choose one of this booking's submitted inspections. |
| `INVALID_KEY` | 400 | Field keys are 2-63 chars: a-z, 0-9, _, starting with a letter. |
| `INVALID_KEY_CHECKS` | 400 | … |
| `INVALID_MEDIA` | 400 | kind must be one of …. |
| `INVALID_METHOD` | 400 | Pick POST, PUT, PATCH, GET or DELETE. |
| `INVALID_NAME` | 400 | Give the integration a name (up to 100 characters). |
| `INVALID_OVERRIDES` | 400 | … |
| `INVALID_PERMISSION` | 400 | Unknown permission '…'. |
| `INVALID_PERMISSIONS` | 400 | permissions must be an object. |
| `INVALID_QUERY` | 400 | Query parameters are a list of up to …. |
| `INVALID_RATING_CONFIG` | 400 | … |
| `INVALID_REASON` | 400 | Choose a reschedule reason from the list. |
| `INVALID_REORDER` | 400 | Send pages, sections and/or fields. |
| `INVALID_RULE` | 400 | … |
| `INVALID_SCHEDULE` | 400 | … |
| `INVALID_SCOPE` | 400 | '…' must be one of: …. |
| `INVALID_SETTINGS` | 400 | Send use_start and/or use_end as true/false. |
| `INVALID_SHARED` | 400 | A shared item needs a kind and a key (a-z, 0-9, _). |
| `INVALID_STAGE` | 409 | A … booking cannot be assigned. |
| `INVALID_TEMPLATE` | 400 | … |
| `INVALID_TEMPLATE_FILE` | 400 | This is not a Vayu report template file. |
| `INVALID_TOGGLE` | 400 | allow_delete must be true or false. |
| `INVALID_TOKEN` | 400 | Send the phone's push token. |
| `INVALID_TYPE` | 400 | Choose an inspection type from the list. |
| `INVALID_URL` | 400 | This URL cannot be used (bad_url). |
| `INVALID_VALUE` | 400 | … must be text of up to … characters. |
| `INVALID_VERSION` | 400 | That form version is not one this lead can use. |
| `IN_USE` | 409 | This item is used by a form; archive it instead. |
| `KEY_IMMUTABLE` | 400 | A library field's key can never change. |
| `KEY_RESERVED` | 400 | Key '…' was used before as a … field; pick another key. |
| `KEY_REVOKED` | 409 | A revoked key cannot be changed. |
| `KEY_TAKEN` | 409 | A form with the key '…' already exists. |
| `LAST_ADMIN` | 400 | There must always be one active admin. |
| `LINKED_LOCKED` | 409 | This section is linked to the library; unlink it to change its structure. |
| `LINK_EXPIRED` | 404 | This download link is invalid or has expired. |
| `LOCKED_HEADER` | 400 | … is set by the system and cannot be changed. |
| `MEDIA_REMOVED` | 410 | This file was deleted after the storage time set in Settings (Photo and video storage). |
| `METHOD_NOT_ALLOWED` | 405 | This endpoint does not take that method. |
| `NOTHING_TO_COPY` | 409 | This form has no published version yet. |
| `NOT_ASSIGNED` | 409 | This lead is no longer assigned to you. |
| `NOT_AUTHENTICATED` | 401 | Sign in first. |
| `NOT_A_DEVICE` | 400 | Only the app sends a heartbeat. |
| `NOT_A_DRAFT` | 409 | Only a draft can be discarded. |
| `NOT_DUPLICABLE` | 400 | Only custom forms can be copied; the booking, start and end forms are the only ones of their kind. |
| `NOT_FOUND` | 404 | No such object (or not one you may see). |
| `NOT_GRANTABLE` | 400 | '…' can only be held by Admin. |
| `NOT_LINKED` | 400 | This item is not linked to the library. |
| `NOT_READY` | 409 | This file is not verified yet. |
| `NOT_STARTED` | 409 | Only a started booking can be force-released. |
| `NOT_SUBMITTED` | 409 | Ratings and Key Checks can be set once the expert submits. |
| `NOT_UPLOADING` | 409 | Start the upload again. |
| `NO_ALERT` | 409 | This booking has no such alert. |
| `NO_APP` | 404 | No app build has been published yet. |
| `NO_BOOKING_FORM` | 409 | Publish the booking form first. |
| `NO_CONFLICT` | 409 | This booking has no conflict to resolve. |
| `NO_DRAFT` | 409 | There is no draft to discard. |
| `NO_INSPECTION` | 404 | This booking has no inspection yet. |
| `NO_INSPECTION_FORM` | 409 | No published inspection form for '…'. |
| `NO_MEDIA` | 404 | There is nothing to download. |
| `NO_REPORT` | 404 | The report is not ready yet. |
| `OLD_BUNDLE` | 400 | … |
| `OPS_UPLOAD_BLOCKED` | 403 | Admin has blocked uploads by Ops on '…'. |
| `OPS_UPLOAD_NOT_ALLOWED` | 403 | Ops can add only photos, videos and files. |
| `OUT_OF_SCOPE` | 403 | This key may not use that form. |
| `PARSE_ERROR` | 400 | The body is not valid JSON (or not a JSON object). |
| `PASSWORD_CHANGE_REQUIRED` | 403 | You must change your password first. |
| `PATH_VALUE_EMPTY` | 400 | … is empty for this booking, so the URL cannot be built. |
| `PERMISSION_DENIED` | 403 | Your role may not do this. |
| `PICTURE_IN_USE` | 409 | A template or shared theme still uses this picture. |
| `PUBLISH_BLOCKED` | 400 | Fix these problems before publishing. |
| `PUSH_BLOCKED` | 409 | Fix these problems first; nothing was changed. |
| `REQUEST_FAILED` | 400 | The request cannot be built: …. |
| `REQUIRED_FILES_MISSING` | 409 | Upload the required files first: …. |
| `REVISION_REQUIRED` | 400 | Send the revision you started from. |
| `RULE_NOT_SELF_CONTAINED` | 400 | A rule uses '…', which is not part of this library item. Put that field in the same library section, or keep this item out of the library. |
| `SHARED_BLOCKED` | 400 | Some templates using this would show fields their form does not have. |
| `SHARED_IN_USE` | 409 | Still used by …. Remove it from those reports first. |
| `STALE_DRAFT` | 409 | The draft changed since you opened it; reload. |
| `STALE_LIBRARY_ITEM` | 409 | Someone saved this item after you opened it; reload to see their changes. |
| `SYSTEM_FIELD` | 400 | System fields cannot go to the library. |
| `SYSTEM_FORM` | 400 | The booking, start and end forms cannot be switched off. |
| `TEMPLATE_EXISTS` | 409 | This form already has a PDF template. |
| `THROTTLED` | 429 | Too many requests; wait and try again. |
| `TOO_LARGE` | 400 | A … may be at most … MB. |
| `TOO_MANY` | 409 | '…' takes at most …. Replace one instead. |
| `TYPE_IMMUTABLE` | 400 | A library field's type can never change. |
| `TYPE_LOCKED` | 409 | The inspection type is locked once the booking has started. |
| `UNKNOWN_ACTION` | 404 | Use assign, cancel, reschedule or change-type. |
| `UNKNOWN_FIELD` | 400 | '…' is not a field of this inspection. |
| `UNKNOWN_MEDIA` | 400 | Add only files you uploaded to this field. |
| `UNKNOWN_VALUE` | 400 | … uses …, which this form and event do not offer. |
| `UPLOAD_NOT_FINISHED` | 409 | The file is still uploading. |
| `USE_ACTION` | 400 | … change through their own actions. |
| `UUID_CONFLICT` | 409 | That request ID belongs to another request. |
| `VERSION_PUBLISHED` | 409 | Published versions cannot be changed. |
| `VIA_SECTION` | 400 | This field is part of a linked section; unlink the section. |
| `WRONG_KIND` | 400 | Expected a … item. |
| `WRONG_VERSION` | 400 | Section belongs to another form version. |
<!-- /table -->
