# Tasks

- [x] 1.1 Delete `k8s/`, recording in the commit that git history is the recovery path
- [x] 1.2 Test that no committed deployment configuration publishes a service beyond loopback, so a future one cannot reintroduce it
- [x] 1.3 Test that no committed configuration carries a working credential
- [x] 1.4 Set `LOAD__DELETE_COMPLETED_JOBS` on the two services that run dlt, leaving failed packages intact
- [x] 1.5 Note the dlt limitation in the deployment guide: the setting is third-party configuration and its silent removal would resume invisible growth
