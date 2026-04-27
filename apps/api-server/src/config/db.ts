import pg from 'pg';
import { drizzle } from 'drizzle-orm/node-postgres';

const { Pool } = pg;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgres://agent:agent_secret@localhost:5432/agent_db',
});

export const db = drizzle(pool);
export { pool };
