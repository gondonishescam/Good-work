function getCart(){try{return JSON.parse(localStorage.getItem('cart'))||[]}catch(e){return[]}}
function setCart(c){try{localStorage.setItem('cart',JSON.stringify(c))}catch(e){}updateCount()}
function updateCount(){var el=document.getElementById('cart-count');if(el)el.textContent=getCart().reduce(function(s,i){return s+i.qty},0)}
function addToCart(id,name,price){var c=getCart(),it=c.find(function(i){return i.id===id});
  if(it)it.qty++;else c.push({id:id,name:name,price:price,qty:1});setCart(c);toast('«'+name+'» в корзине')}
function toast(t){var d=document.createElement('div');d.className='toast';d.innerHTML=t+' · <a href="/cart">Оформить</a>';
  document.body.appendChild(d);setTimeout(function(){d.remove()},2500)}
function filterCat(btn,cat){document.querySelectorAll('.chips .chip').forEach(function(b){b.classList.remove('on')});btn.classList.add('on');
  document.querySelectorAll('[data-cat]').forEach(function(e){e.style.display=!cat||e.dataset.cat===cat?'':'none'})}
function fmt(v){return v.toLocaleString('ru-RU')+' ₽'}
function renderCart(){var box=document.getElementById('cart-items');if(!box)return;var c=getCart();
  if(!c.length){box.innerHTML='<p>Корзина пуста. <a href="/#catalog">Выбрать букет →</a></p>';return recalc()}
  box.innerHTML=c.map(function(i,n){return '<div class="cart-row"><span>'+i.name.replace(/</g,'&lt;')+'</span><span>'+
   '<button type="button" onclick="qty('+n+',-1)">−</button> '+i.qty+' <button type="button" onclick="qty('+n+',1)">+</button></span><b>'+fmt(i.price*i.qty)+'</b></div>'}).join('');recalc()}
function qty(n,d){var c=getCart();c[n].qty+=d;if(c[n].qty<1)c.splice(n,1);setCart(c);renderCart()}
function recalc(){var t=document.getElementById('total');if(!t)return;var s=getCart().reduce(function(a,i){return a+i.price*i.qty},0);
  document.querySelectorAll('input[name=delivery]:checked,input[name=extra]:checked').forEach(function(e){s+=+e.dataset.price});t.textContent=fmt(s)}
function submitOrder(f){var c=getCart();if(!c.length){alert('Корзина пуста');return false}
  document.getElementById('items-field').value=JSON.stringify(c.map(function(i){return{id:i.id,qty:i.qty}}));return true}
updateCount();renderCart();
