(function( search, $, undefined ) {
    //Private Property
    var flow_map = {"FLOW_START": 4, "FLOW_SEARCHING": 6, "FLOW_RESULTS": 0, "FLOW_NO_RESULTS": 2, "FLOW_INITIALIZE_UNKNOWN": 1}
    var current_flow = flow_map["FLOW_START"]
    var sel_search_process;
    var div_search_block;
    var div_search_information_block;
    var row_search_type;
    var sel_search_type;
    var row_search_size;
    var sel_search_size;
    var row_search_value;
    var inp_search_value;
    var row_search_direction;
    var sel_search_direction;
    var btn_search_button;
    var btn_reset_button;
    var div_search_results;
    var list_search_result_list;
    var result_count;
    var result_count_disclaimer;
    var row_search_progress;
    var row_search_initialize_unknown;
    var search_progress;
    var row_search_actions;

    var structure_block;
    var structure_file_select;
    var structure_refresh_button;
    var structure_group_select;
    var structure_items_section;
    var structure_items_body;
    var structure_items_empty;
    var structure_actions_row;
    var structure_run_button;
    var structure_reset_button;
    var structure_results;
    var structure_results_list;
    var structure_results_count;
    var structure_results_empty;

    var switch_search_proximity;
    var inp_search_proximity_address;
    var inp_search_proximity_size;

    var row_search_aligned;
    var switch_search_aligned;

    var li_template = (['<ons-list-item class="result-row">',
          '<ons-row>',
            '<ons-col align="center" width="65%" class="col ons-col-inner">',
              '<ons-row>',
                '<ons-col width="100%" align="center" class="col ons-col-inner address">##address##</ons-col>',
              '</ons-row>',
              '<ons-row>',
                '<ons-col width="100%" align="center" class="col ons-col-inner"><input tabIndex="-1" type="text" id="result_value_##index##" data-address="##address##" name="search_value" class="text-input text-input--material r-value" value="##value##" onkeydown="search.result_change(this)" onblur="search.result_change(this)" autocomplete="chrome-off"></ons-col>',
              '</ons-row>',
            '</ons-col>',
            '<ons-col align="center" width="7%" class="col ons-col-inner">',
                '<label class="checkbox checkbox--material"><input tabIndex="-1" id="search_freeze_##index##" type="checkbox" class="checkbox__input checkbox--material__input freeze" data-address="##address##" onchange="search.result_freeze(this, ##index##)"> <div class="checkbox__checkmark checkbox--material__checkmark"></div>',
            '</ons-col>',
            '<ons-col align="center" width="18%" class="col ons-col-inner">',
                '<ons-col align="center" width="98px" class="col ons-col-inner"><ons-button modifier="quiet" name="add_button" data-address="##address##" onclick="search.copy_result(##index##, this)"><ons-icon icon="md-copy"/></ons-button></ons-col>',
            '</ons-col>',
          '</ons-row>',
      '</ons-list-item>',
    ]).join("\n");


    var current_state = "SEARCH_STATE_START";
    var current_search_type = "exact";
    var current_search_round = 0;
    var current_search_results = []
    var current_process = ""
    var initialized = false
    var value_valid = false
    var proxy_valid = false
    search.updater = null

    var structure_state = {
        active: false,
        files_loaded: false,
        loading_files: false,
        loading_groups: false,
        running: false,
        file: "",
        groups: [],
        group_map: {},
        group: "",
        items: [],
        base_index: null,
        known_values: {},
        results: [],
    }


    //Public Property

    //Public Method
    search.search_type_changed = function(option) {
        update()
    };

    search.search_size_changed = function(option) {
        update()
        if (sel_search_size && sel_search_size.val() === 'structure') {
            set_structure_mode_active(true)
            ensure_structure_files(false)
        } else {
            set_structure_mode_active(false)
        }
    };

    search.search_value_changed = function(value) {
        update()
    }

    search.search_proximity_value_changed = function(value) {
        update()
    }

    search.result_change = function(ele) {
        if(event.key === 'Enter' || event.key === 'Return' || event.keyCode == 13) {
            $.send('/search', {'command': 'SEARCH_WRITE', 'address': ele.dataset.address, 'value': ele.value}, on_search_status)
            ele.blur()
        }
    }

    search.result_freeze = function(ele, index) {
        $.send('/search', {'command': 'SEARCH_FREEZE', 'address': ele.dataset.address, 'freeze': ele.checked}, on_search_status)
    }

    search.on_return_pressed = function(ele) {
        if (!btn_search_button.prop('disabled')) {
            if(event.key === 'Enter' || event.key === 'Return' || event.keyCode == 13) {
                search.on_search_clicked()
                ele.blur()
            }
        }
    }

    search.on_search_clicked = function() {
        if (sel_search_size && sel_search_size.val() === 'structure') {
            run_structure_search()
            return
        }
        var size = sel_search_size.val()
        var type = sel_search_type.val()
        $.send('/search',
        {   "command": "SEARCH_START",
            "size": size,
            "type": type,
            "value": inp_search_value.val(),
            "proximity": JSON.stringify({'enabled': switch_search_proximity.prop('checked'), 'address': inp_search_proximity_address.val(), 'size': inp_search_proximity_size.val()}),
            "aligned": switch_search_aligned.prop('checked'),
         }
        , on_search_status);
        current_flow = flow_map["FLOW_SEARCHING"]
        update()
    };

    search.on_reset_clicked = function() {
        if (sel_search_size && sel_search_size.val() === 'structure') {
            reset_structure_search(true)
            return
        }
        btn_reset_button.attr('disabled', 'disabled')
        btn_search_button.attr('disabled', 'disabled')
        switch_search_aligned.prop('checked', true)
        $.send('/search', { "command": "SEARCH_RESET" }, on_search_status);
    };

    search.on_process_changed = function(process) {
        process_control.request_process(process, 'search', function(result){
            if (!result.success) {
                set_process('_null')
                ons.notification.toast(result.error, { timeout: 4000, animation: 'fall' })
            } else {
                set_process(process)
            }
        })
    };

    search.on_update_process_list = function(process_list_add, process_list_remove) {
        var options = sel_search_process.children('option') ;
        var selected = sel_search_process.find('option:selected')
        if (process_list_remove.includes(selected.val())) {
            div_search_block.hide()
        }
        for (var i=options.length-1; i>=0; i--) {
            var option=options[i]
            if (process_list_remove.includes(option.value)) {
                option.remove()
            }
        }
        var f = sel_search_process.find('option:first')
        for (const item of process_list_add) {
            f.after($('<option>', {value: item, text: item}))
            f = sel_search_process.find('option:last')
        }
    }

    search.on_update_selected_process = function(process_name) {
        var value = sel_search_process.val()
        if (value != process_name){
            set_process(process_name)
        }
    }

    search.on_tab_set = function(tab) {
        if (tab !== 'search') {
            if (search.updater !== null) {
                clearTimeout(search.updater)
                search.updater = null
            }
        } else {
            if (search.updater === null && current_flow === flow_map["FLOW_RESULTS"]) {
                search.updater = setTimeout(request_update, 100)
            }
        }
    };


    search.ready = function()  {
      initialize()
      $('#search_value_div').show()
      $('#search_direction_div').hide()
      $('#search_results').hide();
      $('#search_searching').hide();
      $('#search_result_table').hide();
      $('#search_reset_button').prop("disabled",true);
      $('#search_button').prop("disabled",true);
      $("#search_paste_button").hide()
      $("#search_proximity_paste").hide()

      list_search_result_list.children("ons-list-item").remove()
      for (i=0; i<40; i++) {
        var el = ons.createElement(li_template.replaceAll('##index##', i).replaceAll('##address##', 0).replaceAll('##value##', 0))
        list_search_result_list.append(el)
        $(el).find('input[name="search_value"]').bind('click', function(){ this.select()})
      }
      $("#search_value").bind('click', function(){ this.select()})
    };

    search.copy_result = function(index, element) {
        document.clipboard.copy({'address': current_search_results[index].address.toString(16), 'value': {'Actual': current_search_results[index].value, 'Display': current_search_results[index].value.toString()}})
    }

    search.clipboard_data_copied = function(data) {
        if (has(data, 'aob') || has(data, 'value')) {
            $("#search_paste_button").show()
        }
        if (has(data, 'address') || has(data, 'resolved')) {
            $("#search_proximity_paste").show()
        }
    }

    search.clipboard_data_pasted = function(data, desc) {
        if (desc === 'search') {
            if (sel_search_size.val() === 'array') {
                if (has(data, 'aob')) {
                    inp_search_value.val(data.aob)
                } else {
                    sel_search_size.val('byte_4')
                    update()
                    inp_search_value.val(data.value.Display)
                }
            } else {
                if (has(data, 'value')) {
                    inp_search_value.val(data.value.Display)
                } else {
                    sel_search_size.val('array')
                    update()
                    inp_search_value.val(data.aob)
                }
            }
        } else if (desc === 'proximity') {
            var addr = 'deadbeef'
            if (has(data, 'address')) {
                addr = data.address
            }
            if (has(data, 'resolved')) {
                addr = data.resolved
            }
            inp_search_proximity_address.val(addr)
        }
        update()
    }

    search.clipboard_data_cleared = function() {
        $("#search_paste_button").hide()
        $("#search_proximity_paste").hide()
    }


    //Private Methods
    function on_search_ready() {
        $.send('/search', { "command": "SEARCH_INITIALIZE" }, on_search_status);
    }

    function set_process(process_name) {
        sel_search_process.val(process_name)
        if (process_name === '_null') {
            process_name = ''
        }
        if (process_name.length > 0) {
            div_search_block.show()
            on_search_ready()
        } else {
            div_search_block.hide()
        }
    }

    function on_search_status(result) {
        current_flow = has(result, 'flow') ? result.flow : current_flow
        var repeat = result.repeat || 0
        result.has_error = result.hasOwnProperty('error') && result.error !== ""
        result.error = result.error || ""
        setup_search_type(result)
        setup_search_size(result)
        setup_search_value(result)
        setup_search_proximity(result)
        setup_search_button(result)
        setup_reset_button(result)
        setup_results_progress(result)
        setup_results_list(result)
        if (result.error !== "") {
            ons.notification.toast(result.error, { timeout: 5000, animation: 'fall' })
        }
        if (repeat > 0) {
            setTimeout(function(){
                $.send('/search', { "command": "SEARCH_STATUS" }, on_search_status);
            }, repeat);
        }
        if (search.updater === null && current_flow === flow_map["FLOW_RESULTS"]) {
            search.updater = setTimeout(request_update, 1000)
        } else if (search.updater !== null && current_flow !== flow_map["FLOW_RESULTS"]) {
            clearTimeout(search.updater)
            search.updater = null
        }
    }

    function request_update() {
        $.send('/search', { "command": "SEARCH_RESULT_UPDATE" }, function(result){
            current_flow = has(result, 'flow') ? result.flow : current_flow
            if (current_flow === flow_map["FLOW_RESULTS"]){
                setup_results_list(result)
                if (result.repeat > 0) {
                    search.updater = setTimeout(request_update, result.repeat)
                }
            }
        });
    }

    function setup_search_type(result) {
        if (is_structure_mode_selected()) {
            row_search_type.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                sel_search_type.removeAttr('disabled')
                sel_search_type.find('option[value="equal_to"]').show()
                sel_search_type.find('option[value="greater_than"]').show()
                sel_search_type.find('option[value="less_than"]').show()
                sel_search_type.find('option[value="unknown"]').show()
                sel_search_type.find('option[value="increase"]').hide()
                sel_search_type.find('option[value="decrease"]').hide()
                sel_search_type.find('option[value="unchanged"]').hide()
                sel_search_type.find('option[value="changed"]').hide()
                sel_search_type.find('option[value="changed_by"]').hide()
                sel_search_type.find('option[value="equal_to"]').prop('selected', true)
                if (has(result, "type")) {
                    sel_search_type.val(result.type)
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                sel_search_type.attr('disabled', 'disabled')
                if (has(result, "type")) {
                    sel_search_type.val(result.type)
                }
                break
            case flow_map["FLOW_RESULTS"]:
                sel_search_type.removeAttr('disabled')
                if (has(result, 'size') && result.size === 'array'){
                    sel_search_type.find('option[value="equal_to"]').show()
                    sel_search_type.find('option[value="greater_than"]').hide()
                    sel_search_type.find('option[value="less_than"]').hide()
                    sel_search_type.find('option[value="unknown"]').hide()
                    sel_search_type.find('option[value="increase"]').hide()
                    sel_search_type.find('option[value="decrease"]').hide()
                    sel_search_type.find('option[value="unchanged"]').show()
                    sel_search_type.find('option[value="changed"]').show()
                    sel_search_type.find('option[value="changed_by"]').hide()
                    sel_search_type.find('option[value="equal_to"]').prop('selected', true)
                } else {
                    sel_search_type.find('option[value="equal_to"]').show()
                    sel_search_type.find('option[value="greater_than"]').show()
                    sel_search_type.find('option[value="less_than"]').show()
                    sel_search_type.find('option[value="unknown"]').hide()
                    sel_search_type.find('option[value="increase"]').show()
                    sel_search_type.find('option[value="decrease"]').show()
                    sel_search_type.find('option[value="unchanged"]').show()
                    sel_search_type.find('option[value="changed"]').show()
                    sel_search_type.find('option[value="changed_by"]').show()
                    sel_search_type.find('option[value="equal_to"]').prop('selected', true)
                }
                if (has(result, "type")) {
                    sel_search_type.val(result.type)
                }
                break
            case flow_map["FLOW_NO_RESULTS"]:
                sel_search_type.attr('disabled', 'disabled')
                if (has(result, "type")) {
                    sel_search_type.val(result.type)
                }
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                sel_search_type.removeAttr('disabled')
                sel_search_type.find('option[value="equal_to"]').hide()
                sel_search_type.find('option[value="greater_than"]').hide()
                sel_search_type.find('option[value="less_than"]').hide()
                sel_search_type.find('option[value="unknown"]').hide()
                sel_search_type.find('option[value="increase"]').show()
                sel_search_type.find('option[value="decrease"]').show()
                sel_search_type.find('option[value="unchanged"]').show()
                sel_search_type.find('option[value="changed"]').show()
                sel_search_type.find('option[value="changed_by"]').show()
                sel_search_type.find('option[value="increase"]').prop('selected', true)
                break
        }
    }

    function setup_search_size(result) {
        var structure_active = is_structure_mode_selected()
        set_structure_mode_active(structure_active)
        if (structure_active) {
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                if (has(result, 'type') && (result.type === 'unknown')) {
                    row_search_size.hide()
                    row_search_aligned.hide()
                } else {
                    row_search_size.show()
                    sel_search_size.removeAttr('disabled')
                    sel_search_size.find('option[value="byte_1"]').show()
                    sel_search_size.find('option[value="byte_2"]').show()
                    sel_search_size.find('option[value="byte_4"]').show()
                    sel_search_size.find('option[value="byte_8"]').show()
                    sel_search_size.find('option[value="float"]').show()
                    sel_search_size.find('option[value="array"]').show()
                    sel_search_size.find('option[value="byte_4"]').prop('selected', true)
                    var _size = sel_search_size.val()
                    if (has(result, "size")) {
                        _size = result.size
                        sel_search_size.val(result.size)
                    }
                   if (_size === 'float' || has(result, 'type') && ((result.type === 'greater_than') || (result.type === 'less_than'))) {
                        row_search_aligned.show()
                    } else {
                        row_search_aligned.hide()
                    }
                    switch_search_aligned.removeAttr('disabled')
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                sel_search_size.attr('disabled', 'disabled')
                switch_search_aligned.attr('disabled', 'disabled')
                if (has(result, "size")) {
                    sel_search_size.val(result.size)
                }
                break
            case flow_map["FLOW_RESULTS"]:
                sel_search_size.removeAttr('disabled')
                switch_search_aligned.attr('disabled', 'disabled')
                if (has(result, 'size') && result.size === 'array'){
                    sel_search_size.find('option[value="byte_1"]').hide()
                    sel_search_size.find('option[value="byte_2"]').hide()
                    sel_search_size.find('option[value="byte_4"]').hide()
                    sel_search_size.find('option[value="byte_8"]').hide()
                    sel_search_size.find('option[value="float"]').hide()
                    sel_search_size.find('option[value="array"]').hide()
                    sel_search_size.find('option[value="array"]').prop('selected', true)
                } else {
                    sel_search_size.find('option[value="byte_1"]').show()
                    sel_search_size.find('option[value="byte_2"]').show()
                    sel_search_size.find('option[value="byte_4"]').show()
                    sel_search_size.find('option[value="byte_8"]').show()
                    sel_search_size.find('option[value="float"]').show()
                    sel_search_size.find('option[value="array"]').hide()
                    sel_search_size.find('option[value="byte_4"]').prop('selected', true)
                }
                if (has(result, "size")) {
                    sel_search_size.val(result.size)
                }
                break
            case flow_map["FLOW_NO_RESULTS"]:
                sel_search_size.attr('disabled', 'disabled')
                switch_search_aligned.attr('disabled', 'disabled')
                if (has(result, "size")) {
                    sel_search_size.val(result.size)
                }
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                sel_search_size.removeAttr('disabled')
                switch_search_aligned.removeAttr('disabled')
                sel_search_size.find('option[value="byte_1"]').show()
                sel_search_size.find('option[value="byte_2"]').show()
                sel_search_size.find('option[value="byte_4"]').show()
                sel_search_size.find('option[value="byte_8"]').show()
                sel_search_size.find('option[value="float"]').show()
                sel_search_size.find('option[value="array"]').hide()
                sel_search_size.find('option[value="byte_4"]').prop('selected', true)
                var _size = sel_search_size.val()
                if (has(result, "size")) {
                    _size = result.size
                    sel_search_size.val(result.size)
                }
                if (_size === 'byte_2' || _size === 'byte_4' || _size === 'byte_8' || _size === 'float') {
                    row_search_aligned.show()
                } else {
                    row_search_aligned.hide()
                }
                row_search_size.show()
                break
        }
    }

    function setup_search_value(result) {
        if (is_structure_mode_selected()) {
            row_search_value.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                inp_search_value.removeAttr('disabled')
                if (has(result, 'type') && result.type === 'unknown') {
                    validate_value("_true", 0, 0, result.proximity)
                    row_search_value.hide()
                }else {
                    row_search_value.show()
                    if (has(result, "value") && has(result, "size")) {
                        inp_search_value.val(result.value)
                        validate_value(String(result.value), result.size, result.type, result.proximity)
                    }else {
                        inp_search_value.val("")
                        validate_value("_false", 0, 0, result.proximity)
                    }
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                inp_search_value.attr('disabled', 'disabled')
                if (has(result, "value") && has(result, "size")) {
                    inp_search_value.val(result.value)
                    validate_value(String(result.value), result.size, result.type, result.proximity)
                }else {
                    inp_search_value.val("")
                    validate_value("_false", 0, 0, result.proximity)
                }
                break
            case flow_map["FLOW_RESULTS"]:
                inp_search_value.removeAttr('disabled')
                if (has(result, "value") && has(result, "size")) {
                    inp_search_value.val(result.value)
                    validate_value(String(result.value), result.size, result.type, result.proximity)
                }else {
                    inp_search_value.val("")
                    validate_value("_false", 0, 0, result.proximity)
                }
                break
            case flow_map["FLOW_NO_RESULTS"]:
                inp_search_value.attr('disabled', 'disabled')
                if (has(result, "value") && has(result, "size")) {
                    inp_search_value.val(result.value)
                    validate_value(String(result.value), result.size, result.type, result.proximity)
                }else {
                    inp_search_value.val("")
                    validate_value("_false", 0, 0, result.proximity)
                }
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                row_search_value.hide()
                break
        }
    }

    function setup_search_proximity(result) {
        if (is_structure_mode_selected()) {
            row_search_proximity.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                switch_search_proximity.removeAttr('disabled')
                inp_search_proximity_address.removeAttr('disabled')
                inp_search_proximity_size.removeAttr('disabled')
                break
            case flow_map["FLOW_SEARCHING"]:
                switch_search_proximity.attr('disabled', 'disabled')
                inp_search_proximity_address.attr('disabled', 'disabled')
                inp_search_proximity_size.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                switch_search_proximity.attr('disabled', 'disabled')
                inp_search_proximity_address.attr('disabled', 'disabled')
                inp_search_proximity_size.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_NO_RESULTS"]:
                switch_search_proximity.attr('disabled', 'disabled')
                inp_search_proximity_address.attr('disabled', 'disabled')
                inp_search_proximity_size.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                switch_search_proximity.attr('disabled', 'disabled')
                inp_search_proximity_address.attr('disabled', 'disabled')
                inp_search_proximity_size.attr('disabled', 'disabled')
                break
        }
    }

    function setup_search_button(result) {
        if (is_structure_mode_selected()) {
            btn_search_button.attr('disabled', 'disabled')
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                btn_search_button.attr('disabled', 'disabled')
                if (has(result, 'type') && result.type == 'unknown') {
                    btn_search_button.removeAttr('disabled')
                } else {
                    if (value_valid && proxy_valid) {
                        btn_search_button.removeAttr('disabled')
                    } else {
                        btn_search_button.attr('disabled', 'disabled')
                    }
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                btn_search_button.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                btn_search_button.attr('disabled', 'disabled')
                if (has(result, 'type') && (result.type == 'unknown' || result.type == 'increase' || result.type == 'decrease' || result.type == 'changed' || result.type == 'unchanged')) {
                    btn_search_button.removeAttr('disabled')
                } else {
                    if (value_valid && proxy_valid) {
                        btn_search_button.removeAttr('disabled')
                    } else {
                        btn_search_button.attr('disabled', 'disabled')
                    }
                }
                break
            case flow_map["FLOW_NO_RESULTS"]:
                btn_search_button.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                btn_search_button.removeAttr('disabled')
                break
        }
    }

    function setup_reset_button(result) {
        if (is_structure_mode_selected()) {
            btn_reset_button.attr('disabled', 'disabled')
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                btn_reset_button.attr('disabled', 'disabled')
                btn_reset_button.text('Reset')
                break
            case flow_map["FLOW_SEARCHING"]:
                btn_reset_button.text("Stop")
                btn_reset_button.removeAttr('disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                btn_reset_button.removeAttr('disabled')
                btn_reset_button.text('Reset')
                break
            case flow_map["FLOW_NO_RESULTS"]:
                btn_reset_button.text("Reset")
                btn_reset_button.removeAttr('disabled')
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                btn_reset_button.text("Reset")
                btn_reset_button.removeAttr('disabled')
                break
        }
    }

    function setup_results_progress(result) {
        if (is_structure_mode_selected()) {
            div_search_results.hide()
            row_search_progress.hide()
            row_search_initialize_unknown.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                div_search_results.hide()
                row_search_progress.hide()
                row_search_initialize_unknown.hide()
                break
            case flow_map["FLOW_SEARCHING"]:
                div_search_results.show()
                row_search_progress.show()
                row_search_initialize_unknown.hide()
                search_progress.text(result.progress)
                break
            case flow_map["FLOW_RESULTS"]:
                div_search_results.show()
                row_search_initialize_unknown.hide()
                row_search_progress.hide()
                break
            case flow_map["FLOW_NO_RESULTS"]:
                div_search_results.show()
                row_search_initialize_unknown.hide()
                row_search_progress.hide()
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                div_search_results.show()
                row_search_progress.hide()
                row_search_initialize_unknown.show()
                break
        }
    }
    function setup_results_list(result) {
        if (is_structure_mode_selected()) {
            div_search_results.hide()
            list_search_result_list.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                div_search_results.hide()
                list_search_result_list.hide()
                break
            case flow_map["FLOW_SEARCHING"]:
                div_search_results.show()
                list_search_result_list.hide()
                break
            case flow_map["FLOW_RESULTS"]:
                div_search_results.show()
                list_search_result_list.show()
                result_count.text(result.count)
                if (result.count > 40) {
                    result_count_disclaimer.show()
                } else {
                    result_count_disclaimer.hide()
                }
                populate_results(result.results, result.array)
                break
            case flow_map["FLOW_NO_RESULTS"]:
                div_search_results.show()
                list_search_result_list.show()
                result_count.text(0)
                result_count_disclaimer.hide()
                populate_results([], false)
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                div_search_results.show()
                list_search_result_list.hide()
                result_count.text(0)
                result_count_disclaimer.hide()
                break
        }
    }

    function update() {
        var st = sel_search_type.val()
        var ss = sel_search_size.val()
        var value = inp_search_value.val()
        var proxy = {'proximity': switch_search_proximity.prop('checked'), 'address': inp_search_proximity_address.val(), 'size': inp_search_proximity_size.val()}
        update_search_type(st, ss, value, proxy)
        update_search_size(st, ss, value, proxy)
        update_search_value(st, ss, value, proxy)
        update_search_proximity(st, ss, value, proxy)
        update_search_button(st, ss, value, proxy)
        update_reset_button(st, ss, value, proxy)
        update_results_progress(st, ss, value, proxy)
        update_results_list(st, ss, value, proxy)
        update_structure_controls()
    }

    function is_structure_mode_selected() {
        return sel_search_size && typeof sel_search_size.val === 'function' && sel_search_size.val() === 'structure'
    }

    function set_structure_mode_active(active) {
        if (!structure_block) {
            return
        }
        if (active) {
            if (!structure_state.active) {
                structure_block.show()
                if (structure_actions_row) {
                    structure_actions_row.show()
                }
                if (row_search_actions) {
                    row_search_actions.hide()
                }
                div_search_results.hide()
                row_search_progress.hide()
                row_search_initialize_unknown.hide()
                ensure_structure_files(false)
            }
            if (structure_results) {
                structure_results.toggle(structure_state.results.length > 0)
            }
        } else if (structure_state.active) {
            structure_block.hide()
            if (structure_actions_row) {
                structure_actions_row.hide()
            }
            if (row_search_actions) {
                row_search_actions.show()
            }
            if (structure_results) {
                structure_results.hide()
            }
        }
        structure_state.active = active
        update_structure_controls()
    }

    function structure_show_error(message) {
        if (message) {
            ons.notification.toast(message, { timeout: 4000, animation: 'fall' })
        }
    }

    function ensure_structure_files(force) {
        if (!structure_block || structure_state.loading_files) {
            return
        }
        if (!force && structure_state.files_loaded) {
            return
        }
        structure_state.loading_files = true
        if (structure_file_select) {
            structure_file_select.attr('disabled', 'disabled')
        }
        update_structure_controls()
        $.send('/codelist', { 'command': 'CODELIST_GET' }, function(result) {
            structure_state.loading_files = false
            if (!result) {
                update_structure_controls()
                return
            }
            if (result.error) {
                structure_show_error(result.error)
            }
            var files = Array.isArray(result.files) ? result.files : []
            if (structure_file_select) {
                structure_file_select.find('option[value!=""]').remove()
                files.forEach(function(name) {
                    structure_file_select.append($('<option>', { value: name, text: name }))
                })
            }
            var preferred = structure_state.file || ''
            if (result.file && files.indexOf(result.file) >= 0) {
                preferred = result.file
            } else if (preferred && files.indexOf(preferred) < 0) {
                preferred = ''
            }
            structure_state.files_loaded = true
            structure_state.file = preferred
            if (structure_file_select) {
                structure_file_select.removeAttr('disabled')
                structure_file_select.val(preferred)
            }
            on_structure_file_change(true)
            update_structure_controls()
        })
    }

    function on_structure_file_change(force) {
        if (!structure_file_select) {
            return
        }
        var selected = (structure_file_select.val() || '').trim()
        if (!force && selected === structure_state.file) {
            update_structure_controls()
            return
        }
        structure_state.file = selected
        structure_state.group = ""
        structure_state.groups = []
        structure_state.group_map = {}
        structure_state.items = []
        structure_state.base_index = null
        if (structure_group_select) {
            structure_group_select.find('option[value!=""]').remove()
            structure_group_select.val('')
            structure_group_select.attr('disabled', 'disabled')
        }
        if (structure_items_body) {
            structure_items_body.empty()
        }
        if (structure_items_section) {
            structure_items_section.hide()
        }
        if (structure_items_empty) {
            structure_items_empty.text('Select a rebase group to view its items.')
            structure_items_empty.hide()
        }
        reset_structure_search(true)
        if (!selected) {
            update_structure_controls()
            return
        }
        if (structure_items_section) {
            structure_items_section.show()
        }
        if (structure_items_empty) {
            structure_items_empty.text('Loading group data…')
            structure_items_empty.show()
        }
        load_structure_groups(selected)
    }

    function load_structure_groups(file) {
        if (!file) {
            return
        }
        structure_state.loading_groups = true
        if (structure_group_select) {
            structure_group_select.attr('disabled', 'disabled')
        }
        update_structure_controls()
        $.send('/search', { 'command': 'SEARCH_STRUCTURE_GROUPS', 'file': file }, function(result) {
            structure_state.loading_groups = false
            if (!result) {
                update_structure_controls()
                return
            }
            if (result.error) {
                structure_show_error(result.error)
                if (structure_items_empty) {
                    structure_items_empty.text('Unable to load rebase groups.')
                    structure_items_empty.show()
                }
                update_structure_controls()
                return
            }
            var groups = Array.isArray(result.groups) ? result.groups : []
            structure_state.groups = groups
            structure_state.group_map = {}
            if (structure_group_select) {
                structure_group_select.find('option[value!=""]').remove()
                groups.forEach(function(entry) {
                    structure_state.group_map[entry.name] = entry
                    structure_group_select.append($('<option>', { value: entry.name, text: entry.name }))
                })
            }
            if (groups.length > 0) {
                if (structure_group_select) {
                    structure_group_select.removeAttr('disabled')
                }
                if (structure_items_empty) {
                    structure_items_empty.text('Select a rebase group to view its items.')
                    structure_items_empty.show()
                }
            } else if (structure_items_empty) {
                structure_items_empty.text('No eligible rebase groups were found in this list.')
                structure_items_empty.show()
            }
            structure_state.group = ""
            structure_state.items = []
            structure_state.base_index = null
            update_structure_controls()
        })
    }

    function on_structure_group_change() {
        if (!structure_group_select) {
            return
        }
        var selected = (structure_group_select.val() || '').trim()
        if (!selected || !structure_state.group_map.hasOwnProperty(selected)) {
            structure_state.group = ""
            structure_state.items = []
            structure_state.base_index = null
            reset_structure_search(true)
            if (structure_items_empty) {
                structure_items_empty.text('Select a rebase group to view its items.')
                structure_items_empty.show()
            }
            if (structure_items_body) {
                structure_items_body.empty()
            }
            update_structure_controls()
            return
        }
        var entry = structure_state.group_map[selected]
        structure_state.group = entry.name
        structure_state.known_values = {}
        render_structure_items(entry)
        reset_structure_search(false)
        update_structure_controls()
    }

    function describe_structure_type(value_type, signed) {
        if (value_type === 'float') {
            return 'Float'
        }
        if (value_type === 'array') {
            return 'Array'
        }
        if (typeof value_type === 'string' && value_type.indexOf('byte_') === 0) {
            var size = value_type.split('_')[1]
            var label = size + ' bytes'
            if (size === '1') {
                label = '1 byte'
            }
            if (signed) {
                return label + ' (signed)'
            }
            return label
        }
        return value_type
    }

    function format_structure_offset(offset) {
        var value = Math.abs(Number(offset) || 0)
        var hex = value.toString(16).toUpperCase()
        if (hex.length < 4) {
            hex = hex.padStart(4, '0')
        }
        var prefix = offset >= 0 ? '+' : '-'
        return prefix + '0x' + hex
    }

    function render_structure_items(entry) {
        if (!structure_items_body) {
            return
        }
        structure_items_body.empty()
        structure_state.items = Array.isArray(entry.items) ? entry.items : []
        structure_state.base_index = entry.base_index
        if (structure_state.items.length === 0) {
            if (structure_items_empty) {
                structure_items_empty.text('No address entries were found in this group.')
                structure_items_empty.show()
            }
            return
        }
        if (structure_items_empty) {
            structure_items_empty.hide()
        }
        structure_state.items.forEach(function(item) {
            var row = $('<tr>')
            var item_name = item.name || ('Code #' + item.index)
            var name_cell = $('<td>')
            name_cell.append($('<span>').text(item_name))
            if (item.index === entry.base_index) {
                name_cell.append($('<span>').addClass('structure-base-badge').text('Base'))
            }
            row.append(name_cell)
            row.append($('<td>').text(describe_structure_type(item.type, item.signed)))
            row.append($('<td>').text(format_structure_offset(item.offset)))
            var input_cell = $('<td>')
            var input = $('<input>', {
                'class': 'text-input text-input--material structure-known-input',
                'data-index': item.index,
                'autocomplete': 'off',
                'placeholder': 'Unknown'
            })
            if (item.type === 'float') {
                input.attr('inputmode', 'decimal')
            } else {
                input.attr('inputmode', 'numeric')
            }
            input.on('input', function() {
                var value = $(this).val().trim()
                var key = String(item.index)
                if (value) {
                    structure_state.known_values[key] = value
                } else if (structure_state.known_values.hasOwnProperty(key)) {
                    delete structure_state.known_values[key]
                }
                update_structure_controls()
            })
            var key = String(item.index)
            if (structure_state.known_values.hasOwnProperty(key)) {
                input.val(structure_state.known_values[key])
            }
            input_cell.append(input)
            row.append(input_cell)
            structure_items_body.append(row)
        })
    }

    function reset_structure_search(clear_inputs) {
        structure_state.results = []
        structure_state.running = false
        if (clear_inputs) {
            structure_state.known_values = {}
            if (structure_items_body) {
                structure_items_body.find('input').val('')
            }
        }
        if (structure_results_list) {
            structure_results_list.empty()
        }
        if (structure_results_count) {
            structure_results_count.text('')
        }
        if (structure_results_empty) {
            structure_results_empty.hide()
        }
        if (structure_results) {
            structure_results.hide()
        }
        update_structure_controls()
    }

    function collect_structure_known_values() {
        var payload = {}
        Object.keys(structure_state.known_values).forEach(function(key) {
            var raw = structure_state.known_values[key]
            if (typeof raw === 'string') {
                var trimmed = raw.trim()
                if (trimmed !== '') {
                    payload[key] = trimmed
                }
            }
        })
        return payload
    }

    function run_structure_search() {
        if (!structure_state.active) {
            return
        }
        if (!structure_state.file || !structure_state.group || structure_state.items.length === 0 || structure_state.running) {
            return
        }
        structure_state.running = true
        if (structure_results_empty) {
            structure_results_empty.hide()
        }
        if (structure_results) {
            structure_results.hide()
        }
        update_structure_controls()
        var payload = {
            'command': 'SEARCH_STRUCTURE_RUN',
            'file': structure_state.file,
            'group': structure_state.group,
            'known_values': JSON.stringify(collect_structure_known_values())
        }
        $.send('/search', payload, function(result) {
            structure_state.running = false
            if (!result) {
                update_structure_controls()
                return
            }
            if (result.error) {
                structure_show_error(result.error)
                update_structure_controls()
                return
            }
            render_structure_results(result)
            update_structure_controls()
        })
    }

    function render_structure_results(result) {
        if (!structure_results || !structure_results_list) {
            return
        }
        var hits = Array.isArray(result.results) ? result.results : []
        structure_state.results = hits
        structure_results_list.empty()
        if (structure_results_count) {
            structure_results_count.text('Matches: ' + hits.length)
        }
        if (hits.length === 0) {
            structure_results.show()
            if (structure_results_empty) {
                structure_results_empty.show()
            }
            return
        }
        if (structure_results_empty) {
            structure_results_empty.hide()
        }
        hits.forEach(function(hit) {
            var card = $('<div>').addClass('structure-result-card')
            var header = $('<div>').addClass('structure-result-header')
            header.append($('<div>').text('Base address: 0x' + hit.base_address))
            var apply_button = $('<ons-button modifier="outline">Apply rebase</ons-button>')
            apply_button.on('click', function() {
                apply_structure_rebase(hit.base_index, hit.base_address)
            })
            header.append(apply_button)
            card.append(header)
            var table = $('<table>').addClass('structure-result-items')
            table.append('<thead><tr><th>Item</th><th>Type</th><th>Offset</th><th>Resolved address</th></tr></thead>')
            var tbody = $('<tbody>')
            hit.items.forEach(function(item) {
                var row = $('<tr>')
                var item_name = item.name || ('Code #' + item.index)
                var name_cell = $('<td>')
                name_cell.append($('<span>').text(item_name))
                if (item.index === hit.base_index) {
                    name_cell.append($('<span>').addClass('structure-base-badge').text('Base'))
                }
                row.append(name_cell)
                row.append($('<td>').text(describe_structure_type(item.type, item.signed)))
                row.append($('<td>').text(format_structure_offset(item.offset)))
                row.append($('<td>').text('0x' + item.address))
                tbody.append(row)
            })
            table.append(tbody)
            card.append(table)
            structure_results_list.append(card)
        })
        structure_results.show()
    }

    function apply_structure_rebase(index, address) {
        if (!structure_state.file || !structure_state.group) {
            return
        }
        $.send('/search', {
            'command': 'SEARCH_STRUCTURE_APPLY',
            'file': structure_state.file,
            'group': structure_state.group,
            'index': index,
            'address': address
        }, function(result) {
            if (!result) {
                return
            }
            if (result.error) {
                structure_show_error(result.error)
                return
            }
            ons.notification.toast('Rebased code list using structure hit.', { timeout: 2500, animation: 'fall' })
        })
    }

    function update_structure_controls() {
        if (!structure_actions_row || !structure_run_button) {
            return
        }
        if (!structure_state.active) {
            structure_actions_row.hide()
            if (row_search_actions) {
                row_search_actions.show()
            }
            return
        }
        structure_actions_row.show()
        if (row_search_actions) {
            row_search_actions.hide()
        }
        if (structure_state.running) {
            structure_run_button.attr('disabled', 'disabled')
            structure_run_button.text('Searching…')
        } else {
            var can_run = !!structure_state.file && !!structure_state.group && structure_state.items.length > 0 && !structure_state.loading_groups && !structure_state.loading_files
            if (can_run) {
                structure_run_button.removeAttr('disabled')
            } else {
                structure_run_button.attr('disabled', 'disabled')
            }
            structure_run_button.text('Run structure search')
        }
        var disable_selects = structure_state.running
        if (structure_file_select) {
            if (disable_selects || structure_state.loading_files) {
                structure_file_select.attr('disabled', 'disabled')
            } else {
                structure_file_select.removeAttr('disabled')
            }
        }
        if (structure_refresh_button) {
            if (disable_selects || structure_state.loading_files) {
                structure_refresh_button.attr('disabled', 'disabled')
            } else {
                structure_refresh_button.removeAttr('disabled')
            }
        }
        if (structure_group_select) {
            if (disable_selects || structure_state.loading_groups || !structure_state.file || structure_state.groups.length === 0) {
                structure_group_select.attr('disabled', 'disabled')
            } else {
                structure_group_select.removeAttr('disabled')
            }
        }
        if (structure_state.running || (Object.keys(structure_state.known_values).length === 0 && structure_state.results.length === 0)) {
            structure_reset_button.attr('disabled', 'disabled')
        } else {
            structure_reset_button.removeAttr('disabled')
        }
    }

    function update_search_type(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            row_search_type.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                sel_search_type.removeAttr('disabled')
                switch (_size) {
                    case 'array':
                        row_search_type.show()
                        sel_search_type.find('option[value="equal_to"]').prop('selected', true)
                        sel_search_type.find('option[value!="equal_to"]').hide()
                        break
                    default:
                        row_search_type.show()
                        sel_search_type.find('option[value="equal_to"]').show()
                        sel_search_type.find('option[value="greater_than"]').show()
                        sel_search_type.find('option[value="less_than"]').show()
                        sel_search_type.find('option[value="unknown"]').show()
                        sel_search_type.find('option[value="increase"]').hide()
                        sel_search_type.find('option[value="decrease"]').hide()
                        sel_search_type.find('option[value="unchanged"]').hide()
                        sel_search_type.find('option[value="changed"]').hide()
                        sel_search_type.find('option[value="changed_by"]').hide()
                        break
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                sel_search_type.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                sel_search_type.removeAttr('disabled')
                switch (_size) {
                    case 'array':
                        row_search_type.show()
                        sel_search_type.find('option[value="equal_to"]').show()
                        sel_search_type.find('option[value="greater_than"]').hide()
                        sel_search_type.find('option[value="less_than"]').hide()
                        sel_search_type.find('option[value="unknown"]').hide()
                        sel_search_type.find('option[value="increase"]').hide()
                        sel_search_type.find('option[value="decrease"]').hide()
                        sel_search_type.find('option[value="unchanged"]').show()
                        sel_search_type.find('option[value="changed"]').show()
                        sel_search_type.find('option[value="changed_by"]').hide()

                        break
                    default:
                        row_search_type.show()
                        sel_search_type.find('option[value="equal_to"]').show()
                        sel_search_type.find('option[value="greater_than"]').show()
                        sel_search_type.find('option[value="less_than"]').show()
                        sel_search_type.find('option[value="unknown"]').hide()
                        sel_search_type.find('option[value="increase"]').show()
                        sel_search_type.find('option[value="decrease"]').show()
                        sel_search_type.find('option[value="unchanged"]').show()
                        sel_search_type.find('option[value="changed"]').show()
                        sel_search_type.find('option[value="changed_by"]').show()
                        break
                }
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                sel_search_type.removeAttr('disabled')
                sel_search_type.find('option[value="equal_to"]').hide()
                sel_search_type.find('option[value="greater_than"]').hide()
                sel_search_type.find('option[value="less_than"]').hide()
                sel_search_type.find('option[value="unknown"]').hide()
                sel_search_type.find('option[value="increase"]').show()
                sel_search_type.find('option[value="decrease"]').show()
                sel_search_type.find('option[value="unchanged"]').show()
                sel_search_type.find('option[value="changed"]').show()
                sel_search_type.find('option[value="changed_by"]').show()
                break
        }
    }

    function update_search_size(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            set_structure_mode_active(true)
            return
        }
        set_structure_mode_active(false)
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                sel_search_size.removeAttr('disabled')
                switch (_type) {
                    case 'equal_to':
                        row_search_size.show()
                        sel_search_size.find('option[value="array"]').show()
                        if (_size === 'float') {
                            row_search_aligned.show()
                        } else {
                            row_search_aligned.hide()
                        }
                        break
                    case 'unknown':
                        row_search_size.hide()
                        row_search_aligned.hide()
                        break
                    case 'greater_than':
                    case 'less_than':
                        if (_size === 'byte_2' || _size === 'byte_4' || _size === 'byte_8' ||_size === 'float') {
                            row_search_aligned.show()
                        } else {
                            row_search_aligned.hide()
                        }
                        break
                    default:
                        row_search_size.show()
                        row_search_aligned.hide()
                        sel_search_size.find('option[value="array"]').hide()
                        break
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                sel_search_size.attr('disabled', 'disabled')
                switch_search_aligned.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                sel_search_size.removeAttr('disabled')
                row_search_size.show()
                sel_search_size.find('option[value="array"]').hide()
                switch_search_aligned.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                sel_search_size.removeAttr('disabled')
                sel_search_size.find('option[value="byte_1"]').show()
                sel_search_size.find('option[value="byte_2"]').show()
                sel_search_size.find('option[value="byte_4"]').show()
                sel_search_size.find('option[value="byte_8"]').show()
                sel_search_size.find('option[value="float"]').show()
                sel_search_size.find('option[value="array"]').hide()
                switch_search_aligned.removeAttr('disabled')
                if (_size === 'byte_2' || _size === 'byte_4' || _size === 'byte_8' ||_size === 'float') {
                    row_search_aligned.show()
                } else {
                    row_search_aligned.hide()
                }
                break
        }
    }

    function update_search_value(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            row_search_value.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                inp_search_value.removeAttr('disabled')
                $("#value_header").text("Value")
                if (_type == 'unknown') {
                    row_search_value.hide()
                    validate_value("_true", 0, 0, _proxy)
                } else {
                    row_search_value.show()
                    inp_search_value.attr('inputmode', _size === 'array' ? 'text' : 'decimal')
                    validate_value(_value, _size, _type, _proxy)
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                inp_search_value.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                inp_search_value.removeAttr('disabled')
                if (_type == 'increase' || _type == 'decrease' || _type == 'changed' || _type == 'unchanged') {
                    row_search_value.hide()
                    validate_value("_true", 0, 0, _proxy)
                } else {
                    row_search_value.show()
                    inp_search_value.attr('inputmode', _size === 'array' ? 'text' : 'decimal')
                    validate_value(_value, _size, _type, _proxy)
                }
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                $("#value_header").text("Value")
                if (_type == 'changed_by') {
                    inp_search_value.removeAttr('disabled')
                    row_search_value.show()
                    inp_search_value.attr('inputmode', _size === 'array' ? 'text' : 'decimal')
                    validate_value(_value, _size, _type, _proxy)
                }
                else {
                    row_search_value.hide()
                    validate_value("_true", 0, 0, _proxy)
                }
                break
        }
    }

    function update_search_proximity(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            row_search_proximity.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                switch_search_proximity.removeAttr('disabled')
                inp_search_proximity_address.removeAttr('disabled')
                inp_search_proximity_size.removeAttr('disabled')
                break
            case flow_map["FLOW_SEARCHING"]:
                switch_search_proximity.attr('disabled', 'disabled')
                inp_search_proximity_address.attr('disabled', 'disabled')
                inp_search_proximity_size.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                switch_search_proximity.attr('disabled', 'disabled')
                inp_search_proximity_address.attr('disabled', 'disabled')
                inp_search_proximity_size.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                switch_search_proximity.attr('disabled', 'disabled')
                inp_search_proximity_address.attr('disabled', 'disabled')
                inp_search_proximity_size.attr('disabled', 'disabled')
                break
        }
    }

    function update_search_button(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            btn_search_button.attr('disabled', 'disabled')
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                if (_type == 'unknown' && proxy_valid) {
                    btn_search_button.removeAttr('disabled')
                } else {
                    if (value_valid && proxy_valid) {
                        btn_search_button.removeAttr('disabled')
                    } else {
                        btn_search_button.attr('disabled', 'disabled')
                    }
                }
                break
            case flow_map["FLOW_SEARCHING"]:
                btn_search_button.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                if (_type == 'unknown') {
                    btn_search_button.removeAttr('disabled')
                } else {
                    if (value_valid) {
                        btn_search_button.removeAttr('disabled')
                    } else {
                        btn_search_button.attr('disabled', 'disabled')
                    }
                }
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                if (_type !== 'changed_by') {
                    btn_search_button.removeAttr('disabled')
                } else {
                    if (value_valid) {
                        btn_search_button.removeAttr('disabled')
                    } else {
                        btn_search_button.attr('disabled', 'disabled')
                    }
                }
                break
        }
    }

    function update_reset_button(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            btn_reset_button.attr('disabled', 'disabled')
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                btn_reset_button.text("Reset")
                btn_reset_button.attr('disabled', 'disabled')
                break
            case flow_map["FLOW_SEARCHING"]:
                btn_reset_button.text("Stop")
                btn_reset_button.removeAttr('disabled')
                break
            case flow_map["FLOW_RESULTS"]:
                btn_reset_button.text("Reset")
                btn_reset_button.removeAttr('disabled')
                break
            case flow_map["FLOW_INITIALIZE_UNKNOWN"]:
                btn_reset_button.text("Reset")
                btn_reset_button.removeAttr('disabled')
                break
        }
    }
    function update_results_progress(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            div_search_results.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                div_search_results.hide()
                break
            case flow_map["FLOW_SEARCHING"]:
                div_search_results.show()
                search_progress.text('0')
                break
        }
    }

    function update_results_list(_type, _size, _value, _proxy) {
        if (_size === 'structure') {
            div_search_results.hide()
            list_search_result_list.hide()
            return
        }
        switch (current_flow) {
            case flow_map["FLOW_START"]:
                div_search_results.hide()
                break
            case flow_map["FLOW_SEARCHING"]:
                list_search_result_list.hide()
                break
        }
    }


    function validate_value(_value, _size, _type, _proxy) {
        validate_proximity(_value, _size, _type, _proxy)
        if (_value === "") {
            value_valid = false
            return
        }
        if (_value === '_true') {
            value_valid = true
            return
        } else if (_value === '_false') {
            value_valid = false
            return
        }
        const array_regex = new RegExp('^(?:([0-9A-F]{2}|\\?{2}) )*([0-9A-F]{2}|\\?{2})$');
        if (_size == 'array') {
            value_valid = array_regex.test(_value.toUpperCase())
        } else if (_size == 'float') {
             value_valid = !isNaN(parseFloat(_value)) && isFinite(_value);
        } else {
            if (!Number.isInteger(Number(_value))) {
                value_valid = false
            } else {
                var n = Number(_value)
                switch (_size) {
                    case 'byte_1':
                        value_valid = (n >= -2<<6 && n < 2<<7)
                        break
                    case 'byte_2':
                        value_valid = (n >= -2<<14 && n < 2<<15)
                        break
                    case 'byte_4':
                        value_valid = (n >= -2<<30 && n < 2**32)
                        break
                    case 'byte_8':
                        value_valid = (n >= -(2**63) && n < 2**64)
                        break
                }
            }
        }
    }

    function validate_proximity(_value, _size, _type, _proxy) {
        if (!_proxy || !_proxy.proximity) {
            proxy_valid = true
            return
        }
        var address = _proxy.address
        var proxy_valid_address = /^(?!.{256,})(?!(aux|clock\$|con|nul|prn|com[1-9]|lpt[1-9])(?:$|\.))[^ ][ \.\w-$()+=[\];#@~,&amp;']+[^\. ]:\d+\+[0-9a-f]+$/i.test(address) || /^[0-9A-F]{5,16}$/i.test(address)
        var proxy_valid_size = /^[0-9]+$/.test(_proxy.size) && parseInt(_proxy.size) >= 16 && parseInt(_proxy.size) <= 65536
        proxy_valid = proxy_valid_address && proxy_valid_size
    }

    function populate_results(results, is_array) {
        current_search_results = results
        var elements = $(".result-row")
        for (i=0; i<40; i++) {
            var el = $(elements[i])
            if (i < results.length) {
                var item = results[i]
                var address_element = el.find(".address")
                var value_element = el.find("input[name='search_value']")
                var add_element = el.find("ons-button")
                var freeze_element = el.find(".freeze")
                value_element.attr('inputmode', is_array ? 'text' : 'decimal')
                if (value_element.is(":focus")) {
                    continue
                }
                var addr = (item.address).toString(16).toUpperCase().padStart(16, '0')
                if (address_element.text() !== addr) {
                    address_element.text((item.address).toString(16).toUpperCase().padStart(16, '0'))
                }
                value_element.attr('data-address', item.address)
                freeze_element.attr('data-address', item.address)
                add_element.attr('data-address', item.address)
                value_element.val(item.value)
                el.show()
            } else {
                el.hide()
            }

        }
    }

    function initialize() {
        sel_search_process = $("#search_process")
        div_search_block = $("#search_block")
        div_search_information_block = $("#search_information_block")
        row_search_size = $("#row_search_size");
        sel_search_size = $("#search_size");
        row_search_type = $("#row_search_type");
        sel_search_type = $("#search_type");
        row_search_value = $("#row_search_value");
        inp_search_value = $("#search_value");
        row_search_direction = $("#search_direction_row");
        sel_search_direction = $("#search_direction");
        btn_search_button = $("#search_button");
        btn_reset_button = $("#search_reset_button");
        div_search_results = $("#search_results");
        list_search_result_list = $("#search_result_list");
        result_count = $("#result_count")
        result_count_disclaimer = $("#result_count_disclaimer")
        row_search_initialize_unknown = $("#search_initialize_unknown_row")
        row_search_progress = $("#search_progress_row")
        search_progress = $("#search_progress")
        row_search_actions = $("#search_standard_actions")

        structure_block = $("#structure_search_block")
        structure_file_select = $("#structure_file_selection")
        structure_refresh_button = $("#structure_refresh_files")
        structure_group_select = $("#structure_group_selection")
        structure_items_section = $("#structure_items_section")
        structure_items_body = $("#structure_items_body")
        structure_items_empty = $("#structure_items_empty")
        structure_actions_row = $("#structure_actions_row")
        structure_run_button = $("#structure_run_button")
        structure_reset_button = $("#structure_reset_button")
        structure_results = $("#structure_results")
        structure_results_list = $("#structure_results_list")
        structure_results_count = $("#structure_results_count")
        structure_results_empty = $("#structure_results_empty")

        switch_search_proximity = $("#search_proximity_switch")
        inp_search_proximity_address = $("#search_proximity_address")
        inp_search_proximity_size = $("#search_proximity_size")

        row_search_aligned = $("#row_search_aligned")
        switch_search_aligned = $("#search_aligned_switch")

        structure_refresh_button.on('click', function() { ensure_structure_files(true) })
        structure_file_select.on('change', function() { on_structure_file_change(false) })
        structure_group_select.on('change', on_structure_group_change)
        structure_run_button.on('click', run_structure_search)
        structure_reset_button.on('click', function() { reset_structure_search(true) })

        //$.send('/search', { "command": "SEARCH_INITIALIZE" }, on_search_status);
    };

    function on_unknown_search_selected() {
        switch (current_state) {
            case 'SEARCH_STATE_START':
                hide([row_search_value, row_search_direction])
                disable([$(sel_search_size.children("[value='array']"))])
                break;
            case 'SEARCH_STATE_SEARCHING':
                break;
            case 'SEARCH_STATE_CONTINUE':
                break;
        }
    }

    function on_value_search_selected() {
        switch (current_state) {
            case 'SEARCH_STATE_START':
                hide([row_search_direction])
                show([row_search_value])
                enable([$(sel_search_size.children("[value='array']"))])
                break;
            case 'SEARCH_STATE_SEARCHING':
                break;
            case 'SEARCH_STATE_CONTINUE':
                break;
        }
    }

    function on_process_changed(process) {
        switch (current_state) {
            case 'SEARCH_STATE_START':
                setup_start_state()
                break;
            case 'SEARCH_STATE_SEARCHING':
                $.send('/search', { "command": "SEARCH_RESET" }, on_search_status);
                break;
            case 'SEARCH_STATE_CONTINUE':
                $.send('/search', { "command": "SEARCH_RESET" }, on_search_status);
                break;
        }
    }

    function has(target, path) {
        if (typeof target != 'object' || target == null) {
            return false;
        }
        var parts = path.split('.');

        while(parts.length) {
            var branch = parts.shift();
            if (!(branch in target)) {
                return false;
            }

            target = target[branch];
        }
        return true;
    }

}( window.search = window.search || {}, jQuery ));
