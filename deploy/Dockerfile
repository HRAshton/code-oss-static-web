FROM nginxinc/nginx-unprivileged:1.31.6-alpine@sha256:26b0bf6fbf07297983cb341998d79c831508787de26627dd2a112321b9c3a4af
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/ /srv/code-oss-static-web/
EXPOSE 8080
