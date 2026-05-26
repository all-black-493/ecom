cube('Customers', {
  sql: `SELECT * FROM customers`,

  joins: {
    Orders: { sql: `${CUBE}.id = ${Orders}.customer_id`, relationship: 'hasMany' },
  },

  measures: {
    count:    { type: 'count' },
    lifetimeRevenue: {
      type: 'sum',
      sql: `(SELECT COALESCE(SUM(grand_total), 0) FROM orders o WHERE o.customer_id = ${CUBE}.id)`,
      format: 'currency',
    },
  },

  dimensions: {
    id:            { sql: 'id', type: 'number', primaryKey: true },
    email:         { sql: 'email', type: 'string', shown: false },
    signupChannel: { sql: 'signup_channel', type: 'string' },
    signupCountry: { sql: 'signup_country', type: 'string' },
    signupAt:      { sql: 'created_at', type: 'time' },
    tenureDays: {
      sql: `EXTRACT(DAY FROM (NOW() - created_at))`,
      type: 'number',
    },
  },

  segments: {
    optedInToMarketing: { sql: `${CUBE}.marketing_opt_in = TRUE` },
  },
});
