import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_app/main.dart';

http.Client mockApi({
  bool failure = false,
  void Function(Map<String, dynamic>)? sent,
}) => MockClient((request) async {
  dynamic value;
  switch (request.url.path) {
    case '/capabilities':
      value = {
        'providers': [],
        'tools': [],
        'extensions': ['txt'],
        'max_upload_mb': 100,
      };
      break;
    case '/chats/current':
      value = {'chat_id': 'test', 'title': '새 대화', 'turns': [], 'files': []};
      break;
    case '/chats':
      value = {
        'chats': [
          {'id': 'test', 'title': '새 대화'},
        ],
      };
      break;
    case '/chat/stream':
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      sent?.call(body);
      if (failure) {
        return http.Response(
          jsonEncode({'detail': '테스트 서버 오류'}),
          500,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      }
      return http.Response(
        '${jsonEncode({
          'type': 'done',
          'files': [],
          'turn': {'question': body['message'], 'answer': '정상 답변', 'results': [], 'usage': [], 'files': []},
        })}\n',
        200,
        headers: {'content-type': 'application/x-ndjson; charset=utf-8'},
      );
    default:
      return http.Response('{}', 404);
  }
  return http.Response(
    jsonEncode(value),
    200,
    headers: {'content-type': 'application/json; charset=utf-8'},
  );
});

void main() {
  testWidgets('Enter 전송과 답변 표시', (tester) async {
    var count = 0;
    final client = mockApi(
      sent: (body) {
        count++;
        expect(body['chat_id'], 'test');
        expect(body['message'], 'hello');
      },
    );
    addTearDown(client.close);
    await tester.pumpWidget(MyApp(client: client));
    await tester.pumpAndSettle();
    expect(find.text('생각의 시작, 여기서.'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('messageInput')), 'hello');
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(count, 1);
    expect(find.text('정상 답변'), findsOneWidget);
  });

  testWidgets('실패한 요청은 입력을 복구한다', (tester) async {
    final client = mockApi(failure: true);
    addTearDown(client.close);
    await tester.pumpWidget(MyApp(client: client));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('messageInput')), '질문');
    await tester.pump();
    await tester.tap(find.byKey(const Key('sendButton')));
    await tester.pumpAndSettle();
    final field = tester.widget<TextField>(
      find.byKey(const Key('messageInput')),
    );
    expect(field.controller!.text, '질문');
    expect(find.textContaining('테스트 서버 오류'), findsWidgets);
    expect(
      tester.widget<IconButton>(find.byKey(const Key('sendButton'))).onPressed,
      isNotNull,
    );
  });

  testWidgets('Shift Enter는 전송하지 않는다', (tester) async {
    var count = 0;
    final client = mockApi(sent: (_) => count++);
    addTearDown(client.close);
    await tester.pumpWidget(MyApp(client: client));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('messageInput')), 'hello');
    await tester.pump();
    await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
    await tester.pumpAndSettle();
    expect(count, 0);
  });
}
