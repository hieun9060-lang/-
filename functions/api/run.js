// '지금 실행' 버튼: GitHub Actions 의 monitor.yml 워크플로를 실행한다.
import { guard, json } from '../_lib/access.js';

export async function handleRun({ request, env }, fetchImpl = fetch) {
  const denied = await guard(request, env, fetchImpl);
  if (denied) return denied;
  const repo = (env.GITHUB_REPO || '').trim();
  if (!env.GITHUB_TOKEN || !/^[\w.-]+\/[\w.-]+$/.test(repo)) {
    return json({ detail: '실행 요청 기능이 설정되지 않았습니다. (GITHUB_TOKEN, GITHUB_REPO 필요)' }, 501);
  }
  const res = await fetchImpl(`https://api.github.com/repos/${repo}/actions/workflows/monitor.yml/dispatches`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, Accept: 'application/vnd.github+json', 'User-Agent': 'academy-monitor',
      'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: (env.GITHUB_BRANCH || 'main').trim(), inputs: { mode: 'collect' } }),
  });
  if (res.status === 204) return json({ ok: true });
  return json({ detail: `GitHub 에서 실행 요청을 거부했습니다 (HTTP ${res.status}). 토큰 권한(Actions: Read and write)과 브랜치 이름을 확인하세요.` }, 502);
}

export const onRequestPost = (ctx) => handleRun(ctx);
