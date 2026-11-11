import path from 'node:path';
import { fileURLToPath } from 'node:url';

const website = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export const paths = {
  website,
  repo: path.dirname(website),
  src: path.join(website, 'src'),
  course: path.join(website, 'course'),
  dist: path.join(website, 'dist'),
  references: path.join(website, 'references'),
  appSite: path.join(path.dirname(website), 'src/tum_mcp/bundled/course_app/site'),
};
