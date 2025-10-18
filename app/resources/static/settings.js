var settings = (function(){
  var logState = {
    initialized: false,
    loading: false
  };

  var blacklistState = {
    initialized: false,
    loading: false,
    pending: false
  };
  var blacklistRefreshTimer = null;

  function ready(){
    fetch_logs();
    refresh_blacklist();
  }

  function on_tab_set(ds){
    if (ds === 'settings' && !logState.initialized) {
      fetch_logs();
    }
    if (ds === 'settings' && !blacklistState.initialized){
      refresh_blacklist();
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

  function set_blacklist_status(message){
    $('#blacklist_status').text(message || '');
  }

  function render_blacklist(data){
    var entries = data.blacklist || [];
    var available = data.available || [];

    var list = $('#blacklist_items');
    list.empty();

    if (!entries.length){
      $('#blacklist_empty').show();
    } else {
      $('#blacklist_empty').hide();
      entries.forEach(function(name){
        var item = $('<ons-list-item class="blacklist-item"></ons-list-item>');
        var left = $('<div class="left"></div>');
        var center = $('<div class="center"></div>').text(name);
        var btn = $('<ons-button modifier="quiet"><ons-icon icon="md-delete"></ons-icon></ons-button>');
        btn.attr('data-name', name);
        btn.on('click', function(){ remove_from_blacklist($(this).attr('data-name')); });
        left.append(btn);
        item.append(left).append(center);
        list.append(item);
      });
    }

    var select = $('#blacklist_add_select');
    var previous = select.val();
    select.empty();
    select.append($('<option>', { value: '', text: 'Add process to blacklist...' }));
    available.forEach(function(entry){
      select.append($('<option>', { value: entry.name, text: entry.display }));
    });
    if (available.some(function(entry){ return entry.name === previous; })){
      select.val(previous);
    } else {
      select.val('');
    }
  }

  function refresh_blacklist(btn, options){
    options = options || {};
    var silent = !!options.silent;
    if (blacklistState.loading && !options.force){
      blacklistState.pending = true;
      return;
    }
    blacklistState.loading = true;
    blacklistState.pending = false;
    if (btn){ $(btn).prop('disabled', true); }
    if (!silent){
      set_blacklist_status('Loading blacklist...');
    }
    // Show loading placeholder and hide list while fetching
    $('#blacklist_loading').show();
    $('#blacklist_items').hide();
    $('#blacklist_empty').hide();
    jQuery.send('/settings', { 'command': 'GET_PROCESS_BLACKLIST' }, function(resp){
      blacklistState.loading = false;
      blacklistState.initialized = true;
      if (btn){ $(btn).prop('disabled', false); }
      if (!resp || resp.status !== 'ok'){
        if (!silent){
          set_blacklist_status('Unable to load blacklist.');
          if (ons && ons.notification && ons.notification.toast){
            ons.notification.toast('Failed to load blacklist.', { timeout: 2500 });
          }
        }
        if (blacklistState.pending){
          blacklistState.pending = false;
          schedule_blacklist_refresh();
        }
        $('#blacklist_loading').hide();
        return;
      }
      render_blacklist(resp);
      if (!silent){
        set_blacklist_status('Loaded ' + resp.blacklist.length + ' blacklisted processes.');
      }
      if (blacklistState.pending){
        blacklistState.pending = false;
        schedule_blacklist_refresh();
      }
      // Hide loading and show list (or empty message)
      $('#blacklist_loading').hide();
      if ((resp.blacklist || []).length){
        $('#blacklist_items').show();
      } else {
        $('#blacklist_empty').show();
      }
    });
  }

  function on_blacklist_select_change(select){
    var value = $(select).val();
    if (!value){
      return;
    }
    add_to_blacklist(value, function(success){
      if (success){
        if (ons && ons.notification && ons.notification.toast){
          ons.notification.toast('Added "' + value + '" to blacklist.', { timeout: 2000 });
        }
      } else {
        if (ons && ons.notification && ons.notification.toast){
          ons.notification.toast('Process already blacklisted.', { timeout: 2000 });
        }
      }
    });
  }

  function add_to_blacklist(name, callback){
    if (!name){
      if (callback){ callback(false); }
      return;
    }
    set_blacklist_status('Adding process to blacklist...');
    jQuery.send('/settings', { 'command': 'ADD_PROCESS_BLACKLIST', 'process': name }, function(resp){
      if (!resp){
        set_blacklist_status('Failed to update blacklist.');
        if (callback){ callback(false); }
        return;
      }
      render_blacklist(resp);
      $('#blacklist_add_select').val('');
      var success = resp.status === 'ok';
      set_blacklist_status(success ? 'Process added to blacklist.' : 'Process was already blacklisted.');
      if (callback){ callback(success); }
    });
  }

  function remove_from_blacklist(name){
    if (!name){
      return;
    }
    set_blacklist_status('Removing process from blacklist...');
    jQuery.send('/settings', { 'command': 'REMOVE_PROCESS_BLACKLIST', 'process': name }, function(resp){
      if (!resp){
        set_blacklist_status('Failed to update blacklist.');
        return;
      }
      render_blacklist(resp);
      set_blacklist_status(resp.status === 'ok' ? 'Process removed from blacklist.' : 'Process not currently blacklisted.');
      if (ons && ons.notification && ons.notification.toast && resp.status === 'ok'){
        ons.notification.toast('Removed "' + name + '" from blacklist.', { timeout: 2000 });
      }
    });
  }

  function add_all_to_blacklist(btn){
    var performAdd = function(){
      if (btn){ $(btn).prop('disabled', true); }
      set_blacklist_status('Adding all processes to blacklist...');
      jQuery.send('/settings', { 'command': 'BLACKLIST_ALL_PROCESSES' }, function(resp){
        if (btn){ $(btn).prop('disabled', false); }
        if (!resp){
          set_blacklist_status('Failed to update blacklist.');
          return;
        }
        render_blacklist(resp);
        if (resp.status === 'ok'){
          set_blacklist_status('All running processes added to blacklist.');
          if (ons && ons.notification && ons.notification.toast){
            ons.notification.toast('Blacklisted all running processes.', { timeout: 2000 });
          }
        } else {
          set_blacklist_status('No additional processes to add.');
        }
      });
    };

    try {
      if (ons && ons.notification && ons.notification.confirm){
        ons.notification.confirm({
          title: 'Blacklist All Processes',
          message: 'Add all currently running processes that are not already blacklisted? You can remove entries later.',
          buttonLabels: ['Cancel', 'Blacklist All']
        }).then(function(index){
          if (index === 1){ performAdd(); }
        });
        return;
      }
    } catch (e){ /* ignore */ }
    performAdd();
  }

  function schedule_blacklist_refresh(){
    if (blacklistState.loading){
      blacklistState.pending = true;
      return;
    }
    if (blacklistRefreshTimer){
      clearTimeout(blacklistRefreshTimer);
    }
    blacklistRefreshTimer = setTimeout(function(){
      blacklistRefreshTimer = null;
      refresh_blacklist(null, { silent: true });
    }, 600);
  }

  function on_update_process_list(addList, removeList){
    if ((addList && addList.length) || (removeList && removeList.length)){
      schedule_blacklist_refresh();
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
    refresh_blacklist: refresh_blacklist,
    on_blacklist_select_change: on_blacklist_select_change,
    add_all_to_blacklist: add_all_to_blacklist,
    on_update_process_list: on_update_process_list,
    restart_server: restart_server
  };
})();
