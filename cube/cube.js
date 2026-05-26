// Cube.dev root config. Loaded automatically by the docker image.
// We keep the schema in /model so it's clearly separated from the runtime config.

module.exports = {
  schemaPath: 'model',
  // Cache pre-aggregations on the Cube server. Postgres handles the seed
  // data set under load just fine; pre-aggs become important once we're
  // pointing the same Cube at BigQuery for long-horizon queries.
  scheduledRefreshTimer: 60,
  contextToAppId: ({ securityContext }) => `lumen-${securityContext?.tenant || 'demo'}`,
};
