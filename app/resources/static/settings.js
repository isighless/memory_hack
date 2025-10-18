var settings = (function(){
  function ready(){
    // no-op for now
  }

  function on_tab_set(ds){
    // no-op for now
  }

  function restart_server(btn){
    var doRestart = function(){
      if (btn) { $(btn).prop('disabled', true); }
      $('#restart_status').text('Requesting restart...');
      jQuery.send('/settings', { 'command': 'RESTART_SERVER' }, function(resp){
        $('#restart_status').text('Restarting server...');
        if (ons && ons.notification && ons.notification.toast){
          ons.notification.toast('Restarting server…', {timeout: 1000});
        }
        setTimeout(function(){
          location.reload();
        }, 1200);
      });
    };

    try {
      if (ons && ons.notification && ons.notification.confirm){
        ons.notification.confirm({
          title: 'Confirm Restart',
          message: 'Restart the Memory Hack server now? This will cause unfinished searches to terminate, and you will lose unsaved changes to your code list. The restart usually takes around 30 seconds and you may need to refresh your browser afterwards.',
          buttonLabels: ['Cancel', 'Restart']
        }).then(function(index){
          if (index === 1) { doRestart(); }
        });
        return;
      }
    } catch (e) { /* fall through to immediate restart */ }
    doRestart();
  }

  return {
    ready: ready,
    on_tab_set: on_tab_set,
    restart_server: restart_server
  };
})();
