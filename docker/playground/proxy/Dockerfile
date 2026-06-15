# =============================================================================
# Dakera Playground Sandbox Proxy (DAK-6713)
# Zero runtime dependencies — pure Node.js stdlib, so no `npm install` layer.
# =============================================================================
FROM node:20-alpine

# Run as the unprivileged user that the base image already provides.
WORKDIR /app
COPY --chown=node:node . /app/
USER node

ENV PROXY_PORT=3100 \
    NODE_ENV=production

EXPOSE 3100

# Liveness check hits the proxy's own /health (not the upstream engine).
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=10s \
  CMD node -e "require('http').get('http://127.0.0.1:'+(process.env.PROXY_PORT||3100)+'/health',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "index.js"]
