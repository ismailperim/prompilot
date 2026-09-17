This PromPilot instance watches the demo stack from docker-compose: one Prometheus
server scraping itself and a single node-exporter running inside a container.

- There is exactly one host. Do not break series down by instance unless asked.
- The node-exporter runs in a container without host mounts, so its metrics
  describe the container's view of the machine, not the real host.
- When the user does not say how far back to look, use the dashboard's time range.
