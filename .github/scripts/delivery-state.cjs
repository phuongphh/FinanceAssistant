// Trusted automation: issue closure means implementation done, never deployed.
async function closedIssues({github, context}) {
  const {owner, repo} = context.repo;
  if (context.eventName === 'issues') {
    const issue = context.payload.issue;
    return context.payload.action === 'closed' && issue.state_reason === 'completed'
      ? [issue.number] : [];
  }
  const pr = context.payload.pull_request;
  if (context.eventName !== 'pull_request' || !pr?.merged || pr.base.ref !== 'main') return [];
  const numbers = new Set();
  let cursor = null;
  do {
    const data = await github.graphql(`query($owner:String!,$repo:String!,$number:Int!,$cursor:String) {
      repository(owner:$owner,name:$repo) { pullRequest(number:$number) {
        closingIssuesReferences(first:100,after:$cursor) {
          nodes { number state stateReason repository { nameWithOwner } }
          pageInfo { hasNextPage endCursor }
        }
      } }
    }`, {owner, repo, number:pr.number, cursor});
    const connection = data.repository.pullRequest.closingIssuesReferences;
    for (const i of connection.nodes) {
      if (i.repository.nameWithOwner.toLowerCase() === `${owner}/${repo}`.toLowerCase()
          && i.state === 'CLOSED' && i.stateReason === 'COMPLETED') numbers.add(i.number);
    }
    cursor = connection.pageInfo.hasNextPage ? connection.pageInfo.endCursor : null;
  } while (cursor);
  return [...numbers];
}

async function moveImplementationDone({github, context, core, projectNumber = 4}) {
  const numbers = await closedIssues({github, context});
  if (!numbers.length) return;
  const {owner, repo} = context.repo;
  const data = await github.graphql(`query($owner:String!,$number:Int!) {
    user(login:$owner) { projectV2(number:$number) { id fields(first:100) { nodes {
      ... on ProjectV2SingleSelectField { id name options { id name } }
    } } } }
  }`, {owner, number:projectNumber});
  const project = data.user.projectV2;
  const status = project?.fields.nodes.find(f => f.name === 'Status');
  const done = status?.options.find(o => o.name === 'Done');
  if (!done) throw new Error('Project Status/Done unavailable; no state changed');
  for (const number of numbers) {
    // Re-read state so a delayed/repeated event cannot mark a reopened issue done.
    const {data:issue} = await github.rest.issues.get({owner, repo, issue_number:number});
    if (issue.state !== 'closed' || issue.state_reason !== 'completed') continue;
    let cursor = null;
    do {
      const result = await github.graphql(`query($owner:String!,$repo:String!,$number:Int!,$cursor:String) {
        repository(owner:$owner,name:$repo) { issue(number:$number) {
          projectItems(first:100,after:$cursor) { nodes { id project { id } }
            pageInfo { hasNextPage endCursor } }
        } }
      }`, {owner, repo, number, cursor});
      const items = result.repository.issue.projectItems;
      for (const item of items.nodes.filter(i => i.project.id === project.id)) {
        await github.graphql(`mutation($project:ID!,$item:ID!,$field:ID!,$option:String!) {
          updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,
            fieldId:$field,value:{singleSelectOptionId:$option}}) { projectV2Item { id } }
        }`, {project:project.id,item:item.id,field:status.id,option:done.id});
      }
      cursor = items.pageInfo.hasNextPage ? items.pageInfo.endCursor : null;
    } while (cursor);
    core.info(`#${number}: implementation Done; deployment fields unchanged`);
  }
}
module.exports = {closedIssues, moveImplementationDone};
