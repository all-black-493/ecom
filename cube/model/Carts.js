cube('Carts', {
  sql: `SELECT * FROM carts`,

  measures: {
    count: { type: 'count' },
    abandoned: { type: 'count', filters: [{ sql: `${CUBE}.status = 'abandoned'` }] },
    converted: { type: 'count', filters: [{ sql: `${CUBE}.status = 'converted'` }] },
    abandonmentRate: {
      type: 'number',
      sql: `${abandoned}::float / NULLIF(${count}, 0)`,
      format: 'percent',
    },
  },

  dimensions: {
    id:         { sql: 'id', type: 'number', primaryKey: true },
    status:     { sql: 'status', type: 'string' },
    createdAt:  { sql: 'created_at', type: 'time' },
  },
});
