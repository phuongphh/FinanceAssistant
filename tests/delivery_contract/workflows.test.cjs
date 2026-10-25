const test = require('node:test');
const assert = require('node:assert/strict');
const {closedIssues,moveImplementationDone} = require('../../.github/scripts/delivery-state.cjs');
const {ensurePullRequest} = require('../../.github/scripts/auto-pr.cjs');
const core = {info(){}};
const base = {repo:{owner:'example',repo:'product'}};
const issueEvent = reason => ({...base,eventName:'issues',payload:{action:'closed',issue:{number:1,state_reason:reason}}});
test('manual completion selects only itself, not children or body references',async()=>{
 const ctx=issueEvent('completed');ctx.payload.issue.body='- [ ] #2\nCloses #3';
 assert.deepEqual(await closedIssues({github:{},context:ctx}),[1]);
});
test('not-planned closure is not implementation done',async()=>{
 assert.deepEqual(await closedIssues({github:{},context:issueEvent('not_planned')}),[]);
});
test('prod merge never changes implementation board',async()=>{
 assert.deepEqual(await closedIssues({github:{},context:{...base,eventName:'pull_request',payload:{pull_request:{merged:true,base:{ref:'prod'}}}}}),[]);
});
test('only actual completed closing references in this repository, with pagination',async()=>{
 let calls=0;
 const github={graphql:async(q,v)=>{
  calls++;assert.equal(v.cursor,calls===1?null:'next');
  const node=(number,state='CLOSED',repository='example/product')=>({number,state,stateReason:'COMPLETED',repository:{nameWithOwner:repository}});
  return {repository:{pullRequest:{closingIssuesReferences:{nodes:calls===1?[node(1),node(2,'OPEN'),node(3,'CLOSED','other/repo')]:[node(4)],pageInfo:{hasNextPage:calls===1,endCursor:'next'}}}}};
 }};
 const context={...base,eventName:'pull_request',payload:{pull_request:{number:9,merged:true,base:{ref:'main'},body:'See #99',head:{ref:'issue-88'}}}};
 assert.deepEqual(await closedIssues({github,context}),[1,4]);assert.equal(calls,2);
});
test('delayed completion skips an issue reopened since event',async()=>{
 let mutations=0;
 const github={graphql:async()=>({user:{projectV2:{id:'p',fields:{nodes:[{id:'status',name:'Status',options:[{id:'done',name:'Done'}]}]}}}}),rest:{issues:{get:async()=>({data:{state:'open'}})}}};
 github.graphql = new Proxy(github.graphql,{apply(target,thisArg,args){if(args[0].startsWith('mutation'))mutations++;return target(...args);}});
 await moveImplementationDone({github,context:issueEvent('completed'),core});assert.equal(mutations,0);
});
test('duplicate completion events only set implementation Status; never close or release',async()=>{
 const writes=[];
 const github={rest:{issues:{get:async()=>({data:{state:'closed',state_reason:'completed'}})}},graphql:async(q,v)=>{
  if(q.startsWith('mutation')){writes.push(v);return {};}
  if(q.includes('user(login'))return {user:{projectV2:{id:'p',fields:{nodes:[{id:'status',name:'Status',options:[{id:'done',name:'Done'}]},{id:'release',name:'Delivery status',options:[{id:'released',name:'Released'}]}]}}}};
  return {repository:{issue:{projectItems:{nodes:[{id:'item',project:{id:'p'}}],pageInfo:{hasNextPage:false}}}}};
 }};
 for(let n=0;n<2;n++)await moveImplementationDone({github,context:issueEvent('completed'),core});
 assert.deepEqual(writes,[{project:'p',item:'item',field:'status',option:'done'},{project:'p',item:'item',field:'status',option:'done'}]);
});
function publisherFixture(){
 let prs=[],creates=0;const github={paginate:async()=>prs,rest:{pulls:{list(){},create:async p=>{creates++;const pr={number:7,...p};prs=[pr];return {data:pr};}},repos:{compareCommitsWithBasehead:async()=>({data:{ahead_by:1}})}}};
 return {github,context:{...base,ref:'refs/heads/codex/issue-12-test'},core,count:()=>creates,set:x=>prs=x};
}
test('repeated publisher event produces exactly one PR and no recursive closes',async()=>{
 const f=publisherFixture();const a=await ensurePullRequest(f);const b=await ensurePullRequest(f);
 assert.equal(f.count(),1);assert.equal(a.number,b.number);assert.equal(a.draft,true);assert.match(a.body,/Refs #12/);assert.doesNotMatch(a.body,/Closes #\d/);
});
test('existing closed task PR is preserved instead of creating another',async()=>{
 const f=publisherFixture();f.set([{number:3,state:'closed',body:'original'}]);assert.equal((await ensurePullRequest(f)).body,'original');assert.equal(f.count(),0);
});
test('auto-pr never handles agent-loop or release branches',async()=>{
 for(const ref of ['refs/heads/agent/issue-1-test','refs/heads/claude/merge-prod-release-1']){
  const f=publisherFixture();f.context.ref=ref;await ensurePullRequest(f);assert.equal(f.count(),0);
 }
});
test('concurrent creation 422 reuses verified existing PR',async()=>{
 const f=publisherFixture();f.github.rest.pulls.create=async()=>{f.set([{number:8}]);throw Object.assign(new Error('race'),{status:422});};assert.equal((await ensurePullRequest(f)).number,8);
});
test('non-race 422 is not silently accepted',async()=>{
 const f=publisherFixture();f.github.rest.pulls.create=async()=>{throw Object.assign(new Error('invalid'),{status:422});};await assert.rejects(()=>ensurePullRequest(f),/invalid/);
});
