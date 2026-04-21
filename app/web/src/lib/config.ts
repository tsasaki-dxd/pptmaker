/**
 * Runtime configuration loader.
 *
 * The web app is a static Next.js export deployed to S3. API endpoint,
 * Cognito IDs, etc. are not known at build time — they come from CDK
 * stack outputs and are written to `/config.json` by the deploy job.
 * Every entry point fetches this once at startup.
 */

export interface RuntimeConfig {
  apiEndpoint: string;
  userPoolId: string;
  userPoolClientId: string;
  region: string;
}

let configPromise: Promise<RuntimeConfig> | null = null;

export function getConfig(): Promise<RuntimeConfig> {
  if (!configPromise) {
    configPromise = fetch('/config.json', { cache: 'no-store' })
      .then((r) => {
        if (!r.ok) throw new Error(`config.json fetch failed: ${r.status}`);
        return r.json() as Promise<RuntimeConfig>;
      })
      .catch((err) => {
        configPromise = null; // allow retry on transient failure
        throw err;
      });
  }
  return configPromise;
}
