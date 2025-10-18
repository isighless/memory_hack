var settings = (function(){
  var logState = {
    initialized: false,
    loading: false
  };

  function ready(){
    fetch_logs();
  }

  function on_tab_set(ds){
    if (ds === 'settings' && !logState.initialized) {
      fetch_logs();
    }
  }

  function set_log_status(message){
    $('#server_log_status').text(message || '');
  }

  function set_log_meta(meta){
    if (!meta || !meta.exists) {
      $('#server_log_meta').text('Log file not found.');
      return;
    }

    var sizeText = format_bytes(meta.size || 0);
    var updatedText = meta.modified_at ? format_timestamp(meta.modified_at) : 'Unknown';
    $('#server_log_meta').text('Size: ' + sizeText + ' | Last updated: ' + updatedText);
  }

  function format_bytes(bytes){
    var units = ['B', 'KB', 'MB', 'GB'];
    var val = bytes;
    var unitIndex = 0;
    while (val >= 1024 && unitIndex < units.length - 1){
      val /= 1024;
      unitIndex++;
    }
    return val.toFixed(unitIndex === 0 ? 0 : 1) + ' ' + units[unitIndex];
  }

  function format_timestamp(ts){
    try {
      var date = new Date(ts);
      if (isNaN(date.getTime())){
        return ts;
      }
      return date.toLocaleString();
    } catch (e){
      return ts;
    }
  }

  function fetch_logs(limit){
    if (logState.loading){
      return;
    }
    logState.loading = true;
    set_log_status('Loading logs...');
    var payload = { 'command': 'GET_SERVER_LOG' };
    if (limit){ payload.limit = limit; }
    jQuery.send('/settings', payload, function(resp){
      logState.loading = false;
      logState.initialized = true;
      if (!resp || resp.status !== 'ok'){
        set_log_status('Unable to load logs.');
        if (ons && ons.notification && ons.notification.toast){
          ons.notification.toast('Failed to load logs.', { timeout: 2500 });
        }
        return;
      }
      $('#server_log_view').val(resp.log || '');
      set_log_meta(resp.metadata);
      set_log_status(resp.line_count + ' lines loaded.');
    });
  }

  function refresh_logs(btn){
    if (btn){ $(btn).prop('disabled', true); }
    fetch_logs();
    if (btn){
      setTimeout(function(){ $(btn).prop('disabled', false); }, 600);
    }
  }

  function download_logs(){
    window.location = '/settings/log/download?ts=' + Date.now();
  }

  function clear_logs(btn){
    var executeClear = function(){
      if (btn){ $(btn).prop('disabled', true); }
      set_log_status('Clearing log...');
      jQuery.send('/settings', { 'command': 'CLEAR_SERVER_LOG' }, function(resp){
        if (btn){ $(btn).prop('disabled', false); }
        if (!resp || resp.status !== 'ok'){
          set_log_status('Failed to clear the log file.');
          if (ons && ons.notification && ons.notification.toast){
            ons.notification.toast('Failed to clear the log file.', { timeout: 2500 });
          }
          return;
        }
        $('#server_log_view').val('');
        set_log_meta(resp.metadata);
        set_log_status('Log cleared.');
      });
    };

    try {
      if (ons && ons.notification && ons.notification.confirm){
        ons.notification.confirm({
          title: 'Clear Log',
          message: 'Clear the server log file? This removes the current contents immediately.',
          buttonLabels: ['Cancel', 'Clear']
        }).then(function(index){
          if (index === 1){ executeClear(); }
        });
        return;
      }
    } catch (e){ /* ignore */ }
    executeClear();
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
    refresh_logs: refresh_logs,
    download_logs: download_logs,
    clear_logs: clear_logs,
    restart_server: restart_server
  };
})();
