
/**********************************************************************
*	<a onclick="favorite(window.location,document.title)">加入收藏</a>  *
*	<a onclick="homePage(this,window.location)">设为首页</a>            *
**********************************************************************/

<!--
function favorite(URL, title)
{
    try
    { 
    window.external.AddFavorite(URL, title);
    }catch (e){
        try
        {
            window.sidebar.addPanel(title, URL, "");
        } catch (e){
            alert("加入收藏失败，请使用Ctrl+D进行添加");
        }
    }
}
function homePage(obj,val){
  		try{
           obj.style.behavior='url(#default#homepage)';
           obj.setHomePage(val);
        }catch(e){
                if(window.netscape) {
                        try {
                           netscape.security.PrivilegeManager.enablePrivilege("UniversalXPConnect"); 
                        }catch(e){
                           alert("此操作被浏览器拒绝！"); 
                        }
                        var prefs = Components.classes['@mozilla.org/preferences-service;1'].getService(Components.interfaces.nsIPrefBranch);
                        prefs.setCharPref('browser.startup.homepage',val);
                 }else{
                 alert("此操作被浏览器拒绝！");
                 }
        }
 }
 //-->