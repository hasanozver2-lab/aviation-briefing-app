# Hourly cloud trigger — 2026-10-17

- Provider: cron-job.org; job ID `8665071`, enabled.
- Schedule: `21 * * * *`, Europe/Istanbul (independent of the local computer).
- Target: GitHub `briefing-pipeline.yml`, `workflow_dispatch`, ref `main`.
- Authentication: fine-grained repository token in the remote job's Authorization header. No secret values are stored in this report or repository.
- Existing GitHub schedule remains as fallback; it can cause additional runs.
- First scheduled request: 17:21 Istanbul, HTTP 204 (accepted).
- GitHub run: https://github.com/hasanozver2-lab/aviation-briefing-app/actions/runs/39040373718 — success.
- Published data commit: `16b09b633330376e9ee94fe13d2525e2ad8464e2`, 17:21:37 Istanbul.
- Tests: 751 passed. Application code was not changed for this setup.
- Initial live check returned `status: ok`, but still the 17:10 timestamp while the data branch had the new 17:21 publication. CDN propagation must be distinguished from scheduler failure.

## Maintenance

- Manage the job in the cron-job.org console; disabling this job stops the independent trigger, not GitHub's fallback schedule.
- Renew the GitHub token before its configured expiration and update the job's Authorization header. Never put token values in reports, screenshots or chat.
- A successful trigger confirms GitHub accepted the request, not that collection/publication succeeded. Check the linked Actions run and the live API separately.
- This is an hourly schedule, not a hard delivery-time guarantee: provider outages and GitHub runner queues may delay completion.
