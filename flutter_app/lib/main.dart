import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

const paper = Color(0xFFDCEAF7);
const ink = Color(0xFF26364A);
const navy = Color(0xFF364D70);
const muted = Color(0xFF536A82);
const line = Color(0xFFBCCFE2);

typedef Json = Map<String, dynamic>;
List<Json> objects(dynamic value) => value is List
    ? value.whereType<Map>().map((m) => Map<String, dynamic>.from(m)).toList()
    : <Json>[];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final fontLoader = FontLoader('AppKorean');
  fontLoader.addFont(rootBundle.load('assets/fonts/NotoSansKR.ttf'));
  await fontLoader.load();
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key, this.client});
  final http.Client? client;
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'AI Agent',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      fontFamily: 'AppKorean',
      scaffoldBackgroundColor: paper,
      colorScheme: ColorScheme.fromSeed(
        seedColor: navy,
        primary: navy,
        surface: paper,
      ),
      textTheme: ThemeData.light().textTheme.apply(
        fontFamily: 'AppKorean',
        bodyColor: ink,
        displayColor: ink,
      ),
      dividerColor: line,
    ),
    home: ChatPage(client: client),
  );
}

class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.size = 36});

  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(size * .24),
        child: Image.asset(
          'assets/branding/app_logo.png',
          fit: BoxFit.cover,
          semanticLabel: 'AI Agent 로고',
        ),
      ),
    );
  }
}

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, this.client});
  final http.Client? client;
  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _input = TextEditingController();
  final _focus = FocusNode();
  final _scroll = ScrollController();
  final _scaffold = GlobalKey<ScaffoldState>();
  late final http.Client _client;
  List<Json> _turns = [], _chats = [], _files = [];
  Json _caps = {};
  String? _chatId;
  bool _busy = false, _loading = true, _force = false, _continueCase = false;
  String _status = '', _notice = '';
  double _font = 16, _delayMs = 0;

  String get _base {
    const custom = String.fromEnvironment('API_BASE_URL');
    if (custom.isNotEmpty) return custom.replaceFirst(RegExp(r'/+$'), '');
    return !kIsWeb && defaultTargetPlatform == TargetPlatform.android
        ? 'http://10.0.2.2:8000'
        : 'http://127.0.0.1:8000';
  }

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? http.Client();
    _initialize();
  }

  @override
  void dispose() {
    if (widget.client == null) _client.close();
    _input.dispose();
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  String _error(Object error) =>
      error.toString().replaceFirst('Exception: ', '');

  Future<Json> _json(String path, {bool post = false}) async {
    final uri = Uri.parse('$_base$path');
    final response = await (post ? _client.post(uri) : _client.get(uri))
        .timeout(const Duration(seconds: 20));
    final dynamic data = jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode >= 400) {
      throw Exception(
        data is Map ? data['detail'] : '서버 오류 ${response.statusCode}',
      );
    }
    return Map<String, dynamic>.from(data as Map);
  }

  void _apply(Json data) {
    _chatId = data['chat_id'] as String?;
    _turns = objects(data['turns']);
    _files = objects(data['files']);
  }

  Future<void> _initialize() async {
    setState(() {
      _loading = true;
      _notice = '';
    });
    try {
      final caps = await _json('/capabilities');
      final chat = await _json('/chats/current');
      final list = await _json('/chats');
      if (!mounted) return;
      setState(() {
        _caps = caps;
        _apply(chat);
        _chats = objects(list['chats']);
      });
      _bottom(force: true);
    } catch (e) {
      if (mounted) setState(() => _notice = '서버에 연결하지 못했어요. ${_error(e)}');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openChat({String? id, bool create = false}) async {
    if (_busy || _loading) return;
    setState(() {
      _loading = true;
      _notice = '';
    });
    try {
      final chat = await _json(create ? '/chats' : '/chats/$id', post: create);
      final list = await _json('/chats');
      if (!mounted) return;
      setState(() {
        _apply(chat);
        _chats = objects(list['chats']);
        _continueCase = false;
        _input.clear();
      });
      _bottom(force: true);
    } catch (e) {
      if (mounted) setState(() => _notice = _error(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _bottom({bool force = false}) {
    final follow =
        force ||
        !_scroll.hasClients ||
        _scroll.position.maxScrollExtent - _scroll.offset < 160;
    if (!follow) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  Future<void> _send() async {
    final question = _input.text.trim();
    if (_busy || _loading || question.isEmpty || _chatId == null) return;
    final turn = <String, dynamic>{
      'question': question,
      'answer': '',
      'results': <Json>[],
      'usage': <Json>[],
      'files': <Json>[],
    };
    _focus.unfocus();
    setState(() {
      _busy = true;
      _notice = '';
      _status = '요청을 확인하고 있어요…';
      _turns.add(turn);
      _input.clear();
    });
    _bottom(force: true);
    bool finished = false;
    try {
      final request = http.Request('POST', Uri.parse('$_base/chat/stream'))
        ..headers['Content-Type'] = 'application/json'
        ..body = jsonEncode({
          'message': question,
          'chat_id': _chatId,
          'force_judgment': _force,
          'continue_case': _continueCase,
        });
      final response = await _client.send(request);
      if (response.statusCode != 200) {
        final body = jsonDecode(await response.stream.bytesToString());
        throw Exception(
          body is Map ? body['detail'] : '서버 오류 ${response.statusCode}',
        );
      }
      await for (final row
          in response.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        if (!mounted) return;
        if (row.trim().isEmpty) continue;
        final event = Map<String, dynamic>.from(jsonDecode(row) as Map);
        final kind = event['type'];
        if (kind == 'heartbeat') continue;
        if (kind == 'error') {
          if (event['turn'] is Map) {
            turn.addAll(Map<String, dynamic>.from(event['turn'] as Map));
          }
          throw Exception(event['message']);
        }
        setState(() {
          if (kind == 'status') _status = '${event['text']}';
          if (kind == 'reset') turn['answer'] = '';
          if (kind == 'token') {
            turn['answer'] = '${turn['answer']}${event['text'] ?? ''}';
          }
          if (kind == 'tool_result') (turn['results'] as List).add(event);
          if (kind == 'usage') (turn['usage'] as List).add(event['data']);
          if (kind == 'done') {
            turn.addAll(Map<String, dynamic>.from(event['turn'] as Map));
            _files = objects(event['files']);
            finished = true;
          }
        });
        _bottom();
        if (kind == 'token' && _delayMs > 0) {
          await Future<void>.delayed(Duration(milliseconds: _delayMs.round()));
        }
      }
      if (!finished) {
        throw Exception('연결이 끊겼어요. 서버 처리는 계속될 수 있으니 대화를 다시 열어 결과를 확인해주세요.');
      }
      if (mounted && turn['error'] != null && _input.text.isEmpty) {
        _input.text = question;
      }
      try {
        final list = await _json('/chats');
        if (mounted) setState(() => _chats = objects(list['chats']));
      } catch (_) {
        /* 저장된 답변은 유지하며 다음 새로고침에서 목록을 갱신합니다. */
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        turn['error'] = _error(e);
        _notice = _error(e);
        if (_input.text.isEmpty) _input.text = question;
      });
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _status = '';
        });
      }
    }
  }

  Future<void> _upload() async {
    if (_busy || _loading || _chatId == null) return;
    setState(() {
      _busy = true;
      _notice = '';
      _status = '파일을 선택해 주세요.';
    });
    try {
      final extensions = (_caps['extensions'] as List? ?? []).cast<String>();
      final chosen = await FilePicker.platform.pickFiles(
        allowMultiple: true,
        withData: true,
        type: extensions.isEmpty ? FileType.any : FileType.custom,
        allowedExtensions: extensions.isEmpty ? null : extensions,
      );
      if (chosen == null || !mounted) return;
      for (final file in chosen.files) {
        if (file.size >
            ((_caps['max_upload_mb'] as num?) ?? 100) * 1024 * 1024) {
          throw Exception('${file.name}: 파일 크기 제한을 초과했어요.');
        }
        if (file.bytes == null) throw Exception('${file.name}: 파일을 읽지 못했어요.');
        setState(() => _status = '${file.name} 등록 중…');
        final request =
            http.MultipartRequest(
                'POST',
                Uri.parse('$_base/chats/$_chatId/files'),
              )
              ..files.add(
                http.MultipartFile.fromBytes(
                  'file',
                  file.bytes!,
                  filename: file.name,
                ),
              );
        final response = await _client.send(request);
        final data = jsonDecode(await response.stream.bytesToString()) as Map;
        if (response.statusCode >= 400) throw Exception('${data['detail']}');
        if (!mounted) return;
        setState(() => _files = objects(data['files']));
      }
    } catch (e) {
      if (mounted) setState(() => _notice = _error(e));
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _status = '';
        });
      }
    }
  }

  Future<void> _link(String value) async {
    final uri = value.startsWith('/')
        ? Uri.parse('$_base$value')
        : Uri.tryParse(value);
    if (uri == null || !['http', 'https'].contains(uri.scheme)) return;
    try {
      if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        throw Exception('링크를 열지 못했어요.');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(_error(e))));
      }
    }
  }

  Future<void> _usage({bool all = false}) async {
    try {
      final data = await _json(all ? '/usage' : '/usage?chat_id=$_chatId');
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('${data['scope']} 사용량'),
          content: SizedBox(
            width: 700,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${data['note']}',
                    style: const TextStyle(fontSize: 12, color: muted),
                  ),
                  const SizedBox(height: 16),
                  if (objects(data['summary']).isEmpty)
                    const Text('아직 수집된 사용량이 없어요.'),
                  ...objects(data['summary']).map(
                    (row) => Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${row['서비스']} · ${row['모델']}',
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '입력 ${row['입력']}  /  출력 ${row['출력']}\n합계 ${row['합계']}  ·  기록 ${row['기록 수']}건',
                            ),
                            Text(
                              '${row['상태']}',
                              style: const TextStyle(
                                fontSize: 12,
                                color: muted,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  ExpansionTile(
                    title: const Text('요청별 상세 기록'),
                    children: [
                      ...objects(data['records']).map(
                        (row) => ListTile(
                          title: Text('${row['provider']} · ${row['stage']}'),
                          subtitle: Text(
                            '${row['model']}\n입력 ${row['input_tokens'] ?? '미수신'} · 출력 ${row['output_tokens'] ?? '미수신'}\n${row['note']}',
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('닫기'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) setState(() => _notice = _error(e));
    }
  }

  void _settings() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      backgroundColor: paper,
      builder: (context) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          child: StatefulBuilder(
            builder: (context, update) => Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '나의 에이전트',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w600),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Jev 판단 함께 실행'),
                  subtitle: const Text('주장과 근거의 적합성을 평가합니다.'),
                  value: _force,
                  onChanged: _busy
                      ? null
                      : (v) {
                          setState(() => _force = v);
                          update(() {});
                        },
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('같은 사건 이어서 분석'),
                  value: _continueCase,
                  onChanged: _busy
                      ? null
                      : (v) {
                          setState(() => _continueCase = v);
                          update(() {});
                        },
                ),
                Text('글자 크기 · ${_font.round()}'),
                Slider(
                  value: _font,
                  min: 14,
                  max: 22,
                  divisions: 8,
                  onChanged: (v) {
                    setState(() => _font = v);
                    update(() {});
                  },
                ),
                Text('출력 조각 사이 지연 · ${_delayMs.round()}ms'),
                Slider(
                  value: _delayMs,
                  min: 0,
                  max: 80,
                  divisions: 8,
                  onChanged: (v) {
                    setState(() => _delayMs = v);
                    update(() {});
                  },
                ),
                const Text(
                  '표시 속도만 조절하며 모델의 처리 시간은 바뀌지 않아요.',
                  style: TextStyle(color: muted, fontSize: 12),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: [
                    OutlinedButton(
                      onPressed: _chatId == null
                          ? null
                          : () {
                              Navigator.pop(context);
                              _usage();
                            },
                      child: const Text('현재 대화 사용량'),
                    ),
                    OutlinedButton(
                      onPressed: () {
                        Navigator.pop(context);
                        _usage(all: true);
                      },
                      child: const Text('전체 대화 사용량'),
                    ),
                  ],
                ),
                const Divider(),
                ...objects(_caps['providers']).map(
                  (p) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(
                      p['configured'] == true
                          ? Icons.check_circle_outline
                          : Icons.info_outline,
                      size: 20,
                    ),
                    title: Text('${p['name']} · ${p['model']}'),
                    subtitle: Text(p['configured'] == true ? '키 설정됨' : '키 미설정'),
                  ),
                ),
                Text(
                  '${_caps['note'] ?? ''}',
                  style: const TextStyle(color: muted, fontSize: 12),
                ),
                ExpansionTile(
                  title: const Text('연결된 도구'),
                  children: [
                    ...objects(_caps['tools'])
                        .map((t) => ListTile(title: Text('${t['label']}'))),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _navigation({bool drawer = false}) => Container(
    width: 260,
    color: const Color(0xFFCDDEEF),
    child: SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.all(22),
            child: Row(
              children: [
                BrandLogo(),
                SizedBox(width: 12),
                Text(
                  'AI Agent',
                  style: TextStyle(fontSize: 19, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _busy || _loading
                    ? null
                    : () {
                        if (drawer) Navigator.pop(context);
                        _openChat(create: true);
                      },
                icon: const Icon(Icons.add),
                label: const Text('새 대화'),
              ),
            ),
          ),
          const Padding(
            padding: EdgeInsets.fromLTRB(24, 24, 24, 8),
            child: Text('저장된 대화', style: TextStyle(color: muted, fontSize: 12)),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: _chats.length,
              itemBuilder: (context, i) {
                final chat = _chats[i];
                return ListTile(
                  selected: chat['id'] == _chatId,
                  leading: const Icon(
                    Icons.chat_bubble_outline_rounded,
                    size: 18,
                  ),
                  title: Text(
                    '${chat['title']}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  enabled: !_busy && !_loading,
                  onTap: () {
                    if (drawer) Navigator.pop(context);
                    _openChat(id: '${chat['id']}');
                  },
                );
              },
            ),
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.tune),
            title: const Text('설정 및 사용량'),
            onTap: () {
              if (drawer) Navigator.pop(context);
              _settings();
            },
          ),
        ],
      ),
    ),
  );

  Widget _markdown(String text) => MarkdownBody(
    data: text,
    selectable: true,
    styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
      p: TextStyle(fontSize: _font, height: 1.65, color: ink),
    ),
    onTapLink: (text, href, title) {
      if (href != null) _link(href);
    },
    sizedImageBuilder: (config) => Text(config.alt ?? '이미지 링크'),
  );

  Widget _structured(dynamic data) {
    if (data is List && data.isNotEmpty && data.every((v) => v is Map)) {
      final rows = objects(data);
      final keys = rows.expand((r) => r.keys).toSet().toList();
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: keys.map((k) => DataColumn(label: Text(k))).toList(),
          rows: rows
              .map(
                (r) => DataRow(
                  cells: keys
                      .map(
                        (k) => DataCell(
                          ConstrainedBox(
                            constraints: const BoxConstraints(maxWidth: 240),
                            child: Text(
                              '${r[k] ?? ''}',
                              maxLines: 4,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ),
                      )
                      .toList(),
                ),
              )
              .toList(),
        ),
      );
    }
    if (data is Map) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: data.entries
            .map(
              (e) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${e.key}',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    _structured(e.value),
                  ],
                ),
              ),
            )
            .toList(),
      );
    }
    if (data is List) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: data.map((v) => _structured(v)).toList(),
      );
    }
    return SelectableText(
      '${data ?? '정보 없음'}',
      style: TextStyle(fontSize: _font, height: 1.6),
    );
  }

  Widget _probability(String label, dynamic value) {
    if (value is! num || !value.isFinite || value < 0 || value > 1) {
      return Text('$label: 산출 보류', style: const TextStyle(color: muted));
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$label · ${(value * 100).toStringAsFixed(1)}%'),
          const SizedBox(height: 6),
          LinearProgressIndicator(
            value: value.toDouble(),
            minHeight: 6,
            borderRadius: BorderRadius.circular(6),
          ),
        ],
      ),
    );
  }

  Widget _judgment(Json data) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Jev 판단 분석',
            style: TextStyle(fontWeight: FontWeight.w600, fontSize: 18),
          ),
          const SizedBox(height: 8),
          Text('${data['근거 범위'] ?? ''}', style: const TextStyle(color: muted)),
          if (data['성공'] != true)
            Text('${data['오류'] ?? '평가 안 됨'}')
          else ...[
            Text('${data['평가한 주장'] ?? ''}'),
            Text('${data['판정'] ?? ''}'),
            if (data['판정 코드'] == 'insufficient')
              const Text('판단 보류 · 근거 부족')
            else if (data['판단 확신도'] != null)
              _probability('판정 확신도', data['판단 확신도']),
            ...objects(data['가설별 확률']).map(
              (row) => Padding(
                padding: const EdgeInsets.only(top: 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${row['가설']}',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Text('${row['판정']}'),
                    if (row['확률'] != null)
                      _probability('가설의 모델 추정 확률', row['확률'])
                    else
                      Text('${row['확률 상태'] ?? '산출 보류'}'),
                    if (row['판정 코드'] != 'insufficient' && row['판단 확신도'] != null)
                      _probability('근거 판정 확신도', row['판단 확신도']),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              '모델 추정이며 실제 정답률이 아닙니다. 가설별 확률의 합이 100%일 필요는 없습니다.',
              style: TextStyle(fontSize: 12, color: muted),
            ),
            ExpansionTile(
              title: const Text('평가 근거와 상세 결과'),
              children: [_structured(data)],
            ),
          ],
        ],
      ),
    ),
  );

  Widget _result(Json result) {
    final data = result['data'];
    if (result['name'] == 'evaluate_judgment' && data is Map) {
      return _judgment(Map<String, dynamic>.from(data));
    }
    return ExpansionTile(
      title: Text('${result['label'] ?? result['name']}'),
      childrenPadding: const EdgeInsets.all(12),
      children: [
        if (data is Map && data['뉴스'] is List)
          ...objects(data['뉴스']).map(
            (a) => ListTile(
              title: Text('${a['제목']}'),
              subtitle: Text('${a['요약문'] ?? ''}\n${a['제공 시각'] ?? ''}'),
              trailing: const Icon(Icons.open_in_new, size: 18),
              onTap: a['네이버 뉴스 링크'] == null
                  ? null
                  : () => _link('${a['네이버 뉴스 링크']}'),
            ),
          )
        else if (data is Map && data['결과'] is String)
          _markdown(data['결과'] as String)
        else
          _structured(data),
      ],
    );
  }

  Widget _downloads(List<Json> files) => Wrap(
    spacing: 8,
    runSpacing: 8,
    children: files
        .map(
          (file) => ActionChip(
            avatar: const Icon(Icons.download_outlined, size: 17),
            label: Text('${file['name']}', overflow: TextOverflow.ellipsis),
            onPressed: () => _link('${file['url']}'),
          ),
        )
        .toList(),
  );

  Widget _turn(Json turn) => Padding(
    padding: const EdgeInsets.only(bottom: 28),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerRight,
          child: Container(
            constraints: const BoxConstraints(maxWidth: 560),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFFC4D9EE),
              borderRadius: BorderRadius.circular(20),
            ),
            child: SelectableText(
              '${turn['question']}',
              style: TextStyle(fontSize: _font, height: 1.6),
            ),
          ),
        ),
        const SizedBox(height: 24),
        const Row(
          children: [
            BrandLogo(size: 28),
            SizedBox(width: 10),
            Expanded(
              child: Text(
                'AI Agent',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if ('${turn['answer'] ?? ''}'.isNotEmpty)
          _markdown('${turn['answer']}'),
        if (turn['error'] != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(
              '${turn['error']}',
              style: const TextStyle(color: Color(0xFF9B3434)),
            ),
          ),
        ...objects(turn['results']).map(_result),
        if (objects(turn['files']).isNotEmpty)
          _downloads(objects(turn['files'])),
        Row(
          children: [
            IconButton(
              tooltip: '답변 복사',
              icon: const Icon(Icons.copy_outlined, size: 17),
              onPressed: () async {
                await Clipboard.setData(
                  ClipboardData(text: '${turn['answer'] ?? ''}'),
                );
                if (!mounted) return;
                ScaffoldMessenger.of(context)
                    .showSnackBar(const SnackBar(content: Text('답변을 복사했어요.')));
              },
            ),
            if (turn['elapsed'] is num)
              Text(
                '${(turn['elapsed'] as num).toStringAsFixed(1)}초',
                style: const TextStyle(fontSize: 12, color: muted),
              ),
          ],
        ),
        if (objects(turn['usage']).isNotEmpty)
          ExpansionTile(
            title: const Text('이 답변의 API 사용량'),
            children: objects(turn['usage'])
                .map(
                  (u) => ListTile(
                    title: Text('${u['provider']} · ${u['model']}'),
                    subtitle: Text(
                      '${u['stage']}\n입력 ${u['input_tokens'] ?? '미수신'} · 출력 ${u['output_tokens'] ?? '미수신'} · 합계 ${u['total_tokens'] ?? '미수신'}\n${u['note']}',
                    ),
                  ),
                )
                .toList(),
          ),
      ],
    ),
  );

  Widget _welcome() => Center(
    child: SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const BrandLogo(size: 76),
          const SizedBox(height: 24),
          const Text(
            '생각의 시작, 여기서.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.w500,
              letterSpacing: -1,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            '문서부터 아이디어까지\n나의 도구를 한곳에서.',
            textAlign: TextAlign.center,
            style: TextStyle(color: muted, fontSize: 16, height: 1.7),
          ),
          const SizedBox(height: 24),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 8,
            runSpacing: 8,
            children: [
              _suggestion('뉴스 요약', '오늘 주요 AI 뉴스를 검색하고 요약해 줘.'),
              _suggestion('문서 요약', '첨부한 문서를 읽고 핵심 내용을 요약해 줘.'),
              _suggestion('이미지 분석', '첨부한 이미지를 분석해 줘.'),
              _suggestion(
                '음성 기록',
                '첨부한 음성을 로컬 Whisper로 텍스트로 변환하고 TXT와 CSV로 저장해 줘.',
              ),
            ],
          ),
        ],
      ),
    ),
  );

  Widget _suggestion(String label, String text) => OutlinedButton(
    onPressed: _loading || _busy
        ? null
        : () {
            _input.text = text;
            _input.selection = TextSelection.collapsed(offset: text.length);
            _focus.requestFocus();
          },
    child: Text(label),
  );

  Widget _composer() => Padding(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
    child: Column(
      children: [
        if (_files.isNotEmpty)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            visualDensity: VisualDensity.compact,
            title: Text(
              '대화에 등록된 파일 ${_files.length}개',
              style: const TextStyle(fontSize: 13),
            ),
            children: [_downloads(_files)],
          ),
        Container(
          padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: line),
            borderRadius: BorderRadius.circular(24),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              IconButton(
                tooltip: '파일 첨부',
                onPressed: _busy || _loading || _chatId == null
                    ? null
                    : _upload,
                icon: const Icon(Icons.attach_file),
              ),
              Expanded(
                child: Focus(
                  onKeyEvent: (node, event) {
                    final enter =
                        event.logicalKey == LogicalKeyboardKey.enter ||
                        event.logicalKey == LogicalKeyboardKey.numpadEnter;
                    if (!enter || HardwareKeyboard.instance.isShiftPressed) {
                      return KeyEventResult.ignored;
                    }
                    final composing = _input.value.composing;
                    if (composing.isValid && !composing.isCollapsed) {
                      return KeyEventResult.ignored;
                    }
                    if (event is KeyDownEvent) _send();
                    return KeyEventResult.handled;
                  },
                  child: TextField(
                    key: const Key('messageInput'),
                    controller: _input,
                    focusNode: _focus,
                    minLines: 1,
                    maxLines: 6,
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _send(),
                    decoration: const InputDecoration(
                      hintText: '무엇이든 물어보세요',
                      border: InputBorder.none,
                    ),
                  ),
                ),
              ),
              ValueListenableBuilder<TextEditingValue>(
                valueListenable: _input,
                builder: (context, value, child) => IconButton.filled(
                  key: const Key('sendButton'),
                  tooltip: '메시지 보내기',
                  onPressed:
                      _busy ||
                          _loading ||
                          _chatId == null ||
                          value.text.trim().isEmpty
                      ? null
                      : _send,
                  icon: const Icon(Icons.arrow_upward_rounded),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'AI의 답변은 틀릴 수 있어요. 중요한 내용은 확인해 주세요.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 11, color: muted),
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final wide = constraints.maxWidth >= 1000;
      return Scaffold(
        key: _scaffold,
        drawer: wide ? null : Drawer(child: _navigation(drawer: true)),
        body: Row(
          children: [
            if (wide) _navigation(),
            Expanded(
              child: SafeArea(
                child: Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      child: Row(
                        children: [
                          if (!wide)
                            IconButton(
                              tooltip: '대화 메뉴',
                              onPressed: () =>
                                  _scaffold.currentState?.openDrawer(),
                              icon: const Icon(Icons.menu),
                            ),
                          const Text(
                            'AI Agent',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const Spacer(),
                          IconButton(
                            tooltip: '대화 새로고침',
                            onPressed: _busy || _loading
                                ? null
                                : () {
                                    if (_chatId == null) {
                                      _initialize();
                                    } else {
                                      _openChat(id: _chatId);
                                    }
                                  },
                            icon: const Icon(Icons.refresh),
                          ),
                          IconButton(
                            tooltip: '설정 및 사용량',
                            onPressed: _settings,
                            icon: const Icon(Icons.tune),
                          ),
                        ],
                      ),
                    ),
                    if (_notice.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: Text(
                          _notice,
                          style: const TextStyle(color: Color(0xFF9B3434)),
                        ),
                      ),
                    Expanded(
                      child: Center(
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 850),
                          child: Column(
                            children: [
                              Expanded(
                                child: _loading
                                    ? const Center(
                                        child: CircularProgressIndicator(),
                                      )
                                    : _turns.isEmpty
                                    ? _welcome()
                                    : SingleChildScrollView(
                                        controller: _scroll,
                                        padding: const EdgeInsets.all(24),
                                        child: Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.stretch,
                                          children: _turns.map(_turn).toList(),
                                        ),
                                      ),
                              ),
                              if (_busy)
                                Padding(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 24,
                                    vertical: 8,
                                  ),
                                  child: Row(
                                    children: [
                                      const SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                        ),
                                      ),
                                      const SizedBox(width: 10),
                                      Expanded(
                                        child: Text(
                                          _status,
                                          style: const TextStyle(color: muted),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              _composer(),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      );
    },
  );
}
