# Production edge configuration

Terminate TLS at either an AWS Application Load Balancer or Nginx.  In both
cases, listen publicly only on HTTPS and redirect HTTP with a permanent 301.

For an EC2 Nginx deployment, adapt `nginx/eehook-api.conf.example`, install a
valid certificate (for example, Certbot), and proxy only to Gunicorn on
`127.0.0.1:8000`.  Do not expose Gunicorn's port in the EC2 security group.

For an ALB deployment, configure an HTTP:80 listener whose only action is a
redirect to HTTPS:443; configure the HTTPS listener to forward to a private
target group.  The load balancer must overwrite `X-Forwarded-Proto` with
`https`.  Keep the instance security group limited to the ALB security group.

Set `STOREFRONT_ORIGINS` to every exact HTTPS browser origin allowed to send
credentialed requests.  For a cross-site storefront, set
`JWT_COOKIE_SAMESITE=None`; otherwise keep the default `Lax`.
