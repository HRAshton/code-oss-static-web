FROM public.ecr.aws/nginx/nginx-unprivileged:1.31.6-alpine@sha256:b9241c6e7b8e9a862f129d8d4199ab64b10390949a78bdd5603379b32c844083
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY dist/ /srv/code-oss-static-web/
EXPOSE 8080
