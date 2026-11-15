export type AtlassianProduct = 'jira' | 'confluence';

export interface AtlassianConnectionRequest {
  site_url: string;
  email: string;
  api_token: string;
}

export interface AtlassianProductConnection {
  connected: boolean;
  site_url: string | null;
  email: string | null;
}

export interface AtlassianConnectionStatus {
  jira: AtlassianProductConnection;
  confluence: AtlassianProductConnection;
}
