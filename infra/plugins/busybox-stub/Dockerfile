FROM busybox:1.36
COPY healthcheck.sh /healthcheck.sh
RUN chmod +x /healthcheck.sh
HEALTHCHECK --interval=30s --timeout=5s CMD ["/healthcheck.sh"]
ENV ABS_TENANT_ID="" ABS_PLUGIN_ID=""
USER 65534:65534
CMD ["sh", "-c", "echo \"plugin ${ABS_PLUGIN_ID} live for ${ABS_TENANT_ID}\"; while true; do sleep 30; done"]
