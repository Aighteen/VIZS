import test from "node:test";
import assert from "node:assert/strict";
import {createBridgeHandler} from "./bridge-handler.mjs";
const recipient="synthetic-recipient";
const message={id:"one",direction:"inbound",sender:{id:recipient},content:{type:"text",text:"https://example.com/product"}};
test("only registered direct inbound text is admitted", async()=>{
 let calls=0;
 const handler=createBridgeHandler({recipient,evaluate:async()=>{calls++;return {message_text:"partial"}}});
 const space={type:"dm",send:async()=>{}};
 for(const item of [{...message,direction:"outbound"},{...message,sender:{id:"other"}},{...message,id:""},{...message,content:{type:"text",text:"x".repeat(4001)}}]) assert.equal(await handler.handle(space,item),"ignored");
 assert.equal(await handler.handle({...space,type:"group"},message),"ignored");assert.equal(calls,0);
});
test("concurrent duplicate produces one evaluation and one send",async()=>{
 let calls=0,sends=0;
 const handler=createBridgeHandler({recipient,evaluate:async(payload)=>{calls++;assert.equal(payload.channel,"debug");return {message_text:"[PARTIAL DATA] verify first"}}});
 const space={type:"dm",send:async()=>{sends++}};
 await Promise.all([handler.handle(space,message),handler.handle(space,message)]);
 assert.equal(calls,1);assert.equal(sends,1);assert.equal(handler.exhausted,true);
});
test("evaluation error is explicit and ambiguous sends are not retried",async()=>{
 let sends=0;
 const handler=createBridgeHandler({recipient,evaluate:async()=>{throw new Error("secret")}});
 const space={type:"dm",send:async(body)=>{sends++;assert.ok(body.includes("unavailable"));assert.ok(!body.includes("secret"));throw new Error("ambiguous")}};
 await assert.rejects(handler.handle(space,message));
 assert.equal(await handler.handle(space,message),"ignored");assert.equal(sends,1);
});

test("clarification does not consume the single URL evaluation budget",async()=>{
 let evaluations=0,sends=0,observations=0;
 const handler=createBridgeHandler({recipient,evaluate:async(payload)=>{evaluations++;return {message_text:payload.message_text.includes("https:")?"partial assessment":"Please send a listing URL"}},onSendResult:async(space,sent)=>{observations++;assert.equal(sent.id,"synthetic-send");}});
 const space={type:"dm",send:async()=>{sends++;return {id:"synthetic-send"}}};
 await handler.handle(space,{...message,id:"clarify",content:{type:"text",text:"hello"}});
 assert.equal(handler.exhausted,false);
 await handler.handle(space,message);
 assert.equal(handler.exhausted,true);
 assert.equal(evaluations,2);assert.equal(sends,2);assert.equal(observations,2);
 assert.equal(await handler.handle(space,{...message,id:"second-url"}),"ignored");
});
