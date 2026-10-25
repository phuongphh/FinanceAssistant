// Legacy interactive branches only. agent/issue-* belongs to the loop publisher.
async function ensurePullRequest({github, context, core}) {
  const {owner, repo} = context.repo;
  const branch = context.ref.replace(/^refs\/heads\//, '');
  if (!/^(claude|codex)\//.test(branch) || /^claude\/merge-prod-release-/.test(branch)) return;
  const list = () => github.paginate(github.rest.pulls.list,
    {owner, repo, head:`${owner}:${branch}`, base:'main', state:'all', per_page:100});
  const existing = await list();
  if (existing.length) {
    core.info(`PR #${existing[0].number} already exists (open or closed); leave body/state intact`);
    return existing[0];
  }
  const {data:comparison} = await github.rest.repos.compareCommitsWithBasehead(
    {owner, repo, basehead:`main...${branch}`});
  if (!comparison.ahead_by) { core.info('No commits ahead of main; no PR'); return; }
  const match = branch.match(/(?:^|\/)issue-(\d+)(?:-|$)/);
  const reference = match ? `Refs #${match[1]}\n\n` : '';
  try {
    const {data:pr} = await github.rest.pulls.create({owner, repo, head:branch, base:'main',
      title:`Implementation: ${branch}`, draft:true,
      body:`${reference}## Changes\nDescribe the change and its acceptance criteria.\n\n## Validation\nRecord commands, results, and head SHA.\n\n## Delivery\nImplementation only; no Dev verification or Production release claimed.\n\nList explicit Closes references only for individually completed issues. No automatic parent/child closure.\n`});
    core.info(`Created draft PR #${pr.number}`);return pr;
  } catch (error) {
    if (error.status !== 422) throw error;
    const raced = await list();
    if (!raced.length) throw error;
    core.info(`Concurrent publisher already created PR #${raced[0].number}`);return raced[0];
  }
}
module.exports = {ensurePullRequest};
