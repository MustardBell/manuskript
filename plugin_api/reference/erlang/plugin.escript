#!/usr/bin/env escript
%%! -noshell -kernel standard_io_encoding latin1
%% Dependency-free Erlang reference for the API-1 command profile.

main(_) ->
    io:setopts(standard_io, [binary]),
    loop().

loop() ->
    case read_message() of
        eof -> ok;
        {ok, Message} ->
            case method(Message) of
                exit -> ok;
                initialize ->
                    send_result(request_id(Message), initialize_result()),
                    loop();
                contribution_call ->
                    send_result(request_id(Message), command_result()),
                    loop();
                deactivate ->
                    send_result(request_id(Message), <<"null">>),
                    loop();
                shutdown ->
                    send_result(request_id(Message), <<"null">>),
                    loop();
                notification -> loop()
            end
    end.

read_message() ->
    case read_headers(undefined) of
        eof -> eof;
        {ok, Length} when Length >= 2, Length =< 16777216 ->
            {ok, read_bytes(Length, [])};
        _ -> erlang:error(invalid_content_length)
    end.

read_bytes(0, Parts) ->
    iolist_to_binary(lists:reverse(Parts));
read_bytes(Remaining, Parts) ->
    case file:read(standard_io, Remaining) of
        {ok, Data} when byte_size(Data) > 0 ->
            read_bytes(Remaining - byte_size(Data), [Data | Parts]);
        eof -> erlang:error(incomplete_payload);
        {error, Reason} -> erlang:error({standard_input, Reason})
    end.

read_headers(Length) ->
    case file:read_line(standard_io) of
        eof -> eof;
        {ok, <<"\n">>} -> {ok, Length};
        {ok, <<"\r\n">>} -> {ok, Length};
        {ok, Line} ->
            case re:run(Line, <<"^Content-Length:[[:space:]]*([0-9]+)\\r?\\n$">>,
                        [{capture, [1], binary}, caseless]) of
                {match, [Digits]} when Length =:= undefined ->
                    read_headers(binary_to_integer(Digits));
                {match, [_]} -> erlang:error(duplicate_content_length);
                nomatch -> read_headers(Length)
            end
    end.

method(Message) ->
    Methods = [
        {initialize, <<"\"method\":\"initialize\"">>},
        {contribution_call, <<"\"method\":\"contribution/call\"">>},
        {deactivate, <<"\"method\":\"deactivate\"">>},
        {shutdown, <<"\"method\":\"shutdown\"">>},
        {exit, <<"\"method\":\"exit\"">>}
    ],
    case [Name || {Name, Needle} <- Methods,
                  binary:match(Message, Needle) =/= nomatch] of
        [Name | _] -> Name;
        [] -> notification
    end.

request_id(Message) ->
    case re:run(Message, <<"\"id\":([0-9]+)">>,
                [{capture, [1], binary}]) of
        {match, [Id]} -> Id;
        nomatch -> erlang:error(missing_request_id)
    end.

send_result(Id, Result) ->
    Payload = iolist_to_binary([
        <<"{\"jsonrpc\":\"2.0\",\"id\":" >>, Id,
        <<",\"result\":" >>, Result, <<"}">>
    ]),
    ok = file:write(standard_io, [
        <<"Content-Length: ">>, integer_to_binary(byte_size(Payload)),
        <<"\r\n\r\n">>, Payload
    ]).

initialize_result() ->
    <<"{\"plugin_id\":\"org.manuskript.reference.erlang\","
      "\"api_version\":1,\"protocol_version\":1,\"contributions\":[{"
      "\"declaration\":{\"$kind\":\"record\","
      "\"name\":\"contribution_declaration\",\"version\":1,\"fields\":{"
      "\"kind\":{\"$kind\":\"enum\",\"name\":\"contribution_kind\","
      "\"value\":\"command\"},\"descriptor\":{\"$kind\":\"record\","
      "\"name\":\"extension_descriptor\",\"version\":1,\"fields\":{"
      "\"id\":\"org.manuskript.reference.erlang.command\","
      "\"name\":\"Erlang conformance command\",\"description\":\"\","
      "\"icon\":\"\",\"extensions\":{\"$kind\":\"tuple\",\"items\":[]}}},"
      "\"configuration\":{\"$kind\":\"map\",\"items\":{}}}},"
      "\"operations\":[\"invoke\"]}]}">>.

command_result() ->
    <<"{\"$kind\":\"map\",\"items\":{\"language\":\"erlang\","
      "\"message\":\"Manuskript API 1\"}}">>.
