# Authentication and email setup

The storefront uses the existing Django user model and cookie-based JWT
session. Google OAuth and Gmail SMTP are separate integrations.

## Backend environment

Set these values in the deployment environment or an untracked `.env` file:

```dotenv
GOOGLE_CLIENT_ID=<Google Web application client ID>
SITE_URL=https://eehook.com
STOREFRONT_ORIGINS=https://eehook.com,https://staging.eehook.com,https://eehook-frondent-web.vercel.app

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=eehook.in@gmail.com
EMAIL_HOST_PASSWORD=<16-character Google app password>
DEFAULT_FROM_EMAIL=eehook.in@gmail.com
```

`EMAIL_HOST_PASSWORD` must be an App Password for `eehook.in@gmail.com`, not
the normal Google account password. Never commit it, the Google client secret,
or the Django secret key.

For local development, also allow
`http://localhost:5173,http://127.0.0.1:5173` in `STOREFRONT_ORIGINS` and use
`SITE_URL=http://localhost:5173`.

## Frontend environment

Set the public client ID at build time:

```dotenv
VITE_GOOGLE_CLIENT_ID=<same Google Web application client ID>
VITE_API_BASE_URL=/backend
```

Only the client ID belongs in Vite. Client secrets and SMTP credentials must
remain on the Django server.

## Google Cloud Console

Create or select a **Web application** OAuth client under the project used by
the storefront. Configure the OAuth consent screen with the application name,
support email, developer contact email, and the `openid`, `email`, and
`profile` scopes. While the consent screen is in testing, add each tester's
Google account; publish it when the application is ready for general use.

Add these Authorized JavaScript origins:

```text
http://localhost:5173
http://127.0.0.1:5173
https://eehook.com
https://staging.eehook.com
https://eehook-frondent-web.vercel.app
```

Add these exact Authorized redirect URIs as well. The redirect flow is required
for Safari and Chrome on iOS because of Intelligent Tracking Prevention (ITP):

```text
https://eehook.com/backend/google-login/redirect/
https://staging.eehook.com/backend/google-login/redirect/
https://eehook-frondent-web.vercel.app/backend/google-login/redirect/
```

The React integration keeps the popup credential flow for desktop and Android,
and automatically uses the redirect URI above on iPhone/iPad browsers.

The Django endpoint `POST /google-login/` validates the ID token signature,
issuer, audience, expiry, and verified-email claim with `GOOGLE_CLIENT_ID`.
It links a verified email to the existing unique user or creates one customer
account, then issues the existing HttpOnly JWT cookies. The redirect endpoint
`POST /google-login/redirect/` validates Google's GIS double-submit CSRF token,
performs the same ID-token validation, and issues the same cookies before
returning to the storefront.

## Password reset flow

The relevant endpoints and pages are:

- `POST /forgot-password/` sends a generic response and, for an active account,
  an email containing `${SITE_URL}/reset-password/<uid>/<token>`.
- `POST /reset-password/<uidb64>/<token>/` validates the time-limited Django
  token, changes the password, and blacklists outstanding refresh tokens.
- React pages: `/forgot-password` and `/reset-password/:uidb64/:token`.

The response to a reset request intentionally does not reveal whether an email
exists. Set `PASSWORD_RESET_TIMEOUT` to the desired lifetime in seconds; the
default is one hour.

## Verification

Run the backend security/authentication tests with:

```powershell
.\venv\Scripts\python.exe manage.py test myapp.tests
```

Real Google and Gmail delivery checks require a configured client ID and Gmail
App Password. The repository does not contain those secrets, so they must be
provided by deployment configuration before claiming an end-to-end production
OAuth or email-delivery test has passed.
