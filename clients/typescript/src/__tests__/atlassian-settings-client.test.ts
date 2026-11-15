import { SettingsClient } from '../client/settings-client';

const status = {
  jira: {
    connected: true,
    site_url: 'https://example.atlassian.net',
    email: 'jira@example.com',
  },
  confluence: {
    connected: false,
    site_url: null,
    email: null,
  },
};

function installAtlassianServer() {
  const fetchMock = vi.fn(async () => {
    return new Response(JSON.stringify(status), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  });
  global.fetch = fetchMock as typeof fetch;
  return fetchMock;
}

describe('SettingsClient Atlassian integration', () => {
  it('uses independent product endpoints and typed credentials', async () => {
    const fetchMock = installAtlassianServer();
    const client = new SettingsClient({ host: 'http://example.com' });

    await expect(client.getAtlassianIntegration()).resolves.toEqual(status);
    await expect(
      client.connectAtlassianProduct('jira', {
        site_url: 'https://example.atlassian.net',
        email: 'jira@example.com',
        api_token: 'jira-secret',
      })
    ).resolves.toEqual(status);
    await expect(client.disconnectAtlassianProduct('jira')).resolves.toEqual(status);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://example.com/api/v1/integrations/atlassian',
      expect.objectContaining({ method: 'GET' })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://example.com/api/v1/integrations/atlassian/jira',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({
          site_url: 'https://example.atlassian.net',
          email: 'jira@example.com',
          api_token: 'jira-secret',
        }),
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      'http://example.com/api/v1/integrations/atlassian/jira',
      expect.objectContaining({ method: 'DELETE' })
    );
  });
});
