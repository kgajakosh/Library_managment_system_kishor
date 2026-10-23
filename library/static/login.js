'use strict';
const form=document.querySelector('#login-form');
const error=document.querySelector('#error');
const submit=document.querySelector('#submit');
form.addEventListener('submit',async event=>{
  event.preventDefault();
  error.textContent='';
  submit.disabled=true;
  try{
    const data=Object.fromEntries(new FormData(form));
    const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json','X-Library-Request':'1'},body:JSON.stringify(data)});
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'Could not sign in.');
    window.location.replace('/');
  }catch(e){error.textContent=e.message||'Could not sign in.';}
  finally{submit.disabled=false;}
});
