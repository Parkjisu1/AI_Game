#!/usr/bin/env node
/**
 * C# Source Code Parser for AI Code Generation System
 * Layer > Genre > Role > Tag 분류 체계 적용
 * v4.0 - Enriched schema: unity_config, integration, recipe 추가
 *       - MongoDB + 로컬 dual write
 *       - 프로젝트 단위 파싱 (project 필드)
 *       - Cross-file integration 분석
 */

const fs = require('fs');
const path = require('path');

// ============================================================
// Configuration
// ============================================================

// Role 패턴 (파일명 기반 - 우선순위 5)
const ROLE_NAME_PATTERNS = {
    'Manager': [/.*Manager$/],
    'Controller': [/.*Controller$/],
    'Calculator': [/.*Calculator$/, /.*Calc$/],
    'Processor': [/.*Processor$/],
    'Handler': [/.*Handler$/],
    'Listener': [/.*Listener$/],
    'Provider': [/.*Provider$/],
    'Factory': [/.*Factory$/],
    'Service': [/.*Service$/],
    'Validator': [/.*Validator$/],
    'Converter': [/.*Converter$/],
    'Builder': [/.*Builder$/],
    'Pool': [/.*Pool$/, /.*Pooler$/],
    'State': [/.*State$/],
    'Command': [/.*Command$/, /.*Cmd$/],
    'Observer': [/.*Observer$/],
    'Helper': [/.*Helper$/, /.*Util$/, /.*Utils$/, /.*Utility$/],
    'Wrapper': [/.*Wrapper$/],
    'Context': [/.*Context$/, /.*Ctx$/],
    'Config': [/.*Config$/, /.*Settings$/, /.*Configuration$/],
    'Message': [/.*Msg$/, /.*Message$/],
    'Data': [/.*Data$/, /.*Info$/, /.*DTO$/],
    'Table': [/.*Table$/],
    'View': [/.*Page$/, /.*Popup$/, /.*Win$/, /.*Window$/, /.*Panel$/, /.*Dialog$/],
    'UX': [/.*Effect$/, /.*Tweener$/, /.*Performer$/, /.*Presenter$/, /.*Particle$/],
};

// 상속 기반 Role (우선순위 2)
const ROLE_BASE_CLASS = {
    'Manager': ['Singleton'],
    'StateHandler': ['StateMachineBehaviour'],
    'Config': ['ScriptableObject'],
    'View': ['UIBase', 'PageBase', 'PopupBase', 'WindowBase', 'PanelBase'],
    'Entity': ['PooledGameObject', 'PooledObject'],
    'Model': ['UserData', 'SaveData'],
};

// 인터페이스 기반 Role (우선순위 3)
const ROLE_INTERFACE = {
    'Message': ['IMessageAction', 'IMessage'],
    'Controller': ['IMessagePort', 'IMessageController'],
    'Service': ['IInjectable', 'IService'],
};

const LAYER_KEYWORDS = {
    'Core': ['Singleton', 'Pool', 'Event', 'Util', 'Extension', 'Base', 'Common', 'Framework'],
    'Game': ['Page', 'Popup', 'Win', 'Element', 'HUD', 'Panel', 'Dialog', 'Toast'],
};

// Domain 강제 키워드 (Core보다 우선)
const DOMAIN_FORCE_KEYWORDS = ['Battle', 'Character', 'Inventory', 'Quest', 'Skill', 'Item', 'Shop', 'Gacha'];

const GENRE_KEYWORDS = {
    'RPG': ['Battle', 'Combat', 'Character', 'Enemy', 'Boss', 'Skill', 'Buff', 'Damage', 'Item', 'Quest', 'Dungeon', 'Raid', 'Equipment', 'Inventory'],
    'Idle': ['Idle', 'Offline', 'AutoPlay', 'AFK', 'Prestige', 'Rebirth'],
    'Merge': ['Merge', 'Combine', 'Grid', 'Cell', 'Generator'],
    'SLG': ['Strategy', 'Territory', 'Troop', 'Alliance', 'War'],
    'Tycoon': ['Business', 'Revenue', 'Customer', 'Staff', 'Shop', 'Store', 'Money', 'Profit'],
    'Simulation': ['Resource', 'Building', 'Construct', 'Timer', 'Production'],
    'Puzzle': ['Board', 'Piece', 'Match', 'Tile', 'Combo', 'Puzzle', 'Sort', 'Block', 'Grid'],
    'Casual': ['Touch', 'Tap', 'Swipe', 'Drop', 'Catch', 'Collect'],
};

const UNITY_LIFECYCLE = new Set(['Awake', 'Start', 'Update', 'FixedUpdate', 'LateUpdate',
    'OnEnable', 'OnDisable', 'OnDestroy', 'OnApplicationPause',
    'OnApplicationQuit', 'OnGUI', 'OnTriggerEnter', 'OnTriggerExit',
    'OnTriggerEnter2D', 'OnTriggerExit2D', 'OnTriggerStay', 'OnTriggerStay2D',
    'OnCollisionEnter', 'OnCollisionExit', 'OnCollisionEnter2D', 'OnCollisionExit2D',
    'OnMouseDown', 'OnMouseUp', 'OnMouseDrag', 'OnBecameVisible', 'OnBecameInvisible',
    'OnDrawGizmos', 'OnValidate', 'Reset']);

const COMMON_METHODS = new Set(['Init', 'Initialize', 'Refresh', 'Reset', 'Clear', 'Dispose',
    'ToString', 'GetHashCode', 'Equals', 'GetType']);

// Major Tag patterns (메서드명 prefix → 대기능 Tag)
const MAJOR_TAG_PATTERNS = {
    'StateControl': [/^Start/, /^Begin/, /^Init/, /^Enable/, /^Open/, /^Close/, /^End/, /^Stop/, /^Disable/],
    'ValueModification': [/^Set/, /^Add/, /^Subtract/, /^Multiply/, /^Increase/, /^Decrease/, /^Modify/, /^Change/],
    'ConditionCheck': [/^Check/, /^Is/, /^Has/, /^Can/, /^Validate/, /^Should/],
    'ResourceTransfer': [/^Give/, /^Take/, /^Transfer/, /^Send/, /^Receive/, /^Buy/, /^Sell/],
    'DataSync': [/^Save/, /^Load/, /^Sync/, /^Update/, /^Refresh/, /^Fetch/],
    'FlowControl': [/^Execute/, /^Run/, /^Process/, /^Handle/, /^Do/],
    'ResponseTrigger': [/^On/, /^Respond/, /^React/, /^Trigger/, /^Fire/, /^Emit/]
};

// Minor Tag patterns (메서드명 prefix → 소기능 Tag)
const MINOR_TAG_PATTERNS = {
    'Compare': [/^Compare/, /^Sort/],
    'Calculate': [/^Calculate/, /^Compute/, /^Eval/],
    'Find': [/^Find/, /^Search/, /^Get/, /^Lookup/],
    'Validate': [/^Validate/, /^Verify/, /^Assert/],
    'Assign': [/^Assign/, /^Set/, /^Apply/],
    'Notify': [/^Notify/, /^Publish/, /^Broadcast/, /^Dispatch/],
    'Delay': [/^Wait/, /^Delay/, /^Yield/],
    'Spawn': [/^Spawn/, /^Create/, /^Instantiate/, /^Generate/],
    'Despawn': [/^Despawn/, /^Destroy/, /^Remove/, /^Kill/, /^Delete/],
    'Iterate': [/^ForEach/, /^Iterate/, /^Loop/, /^Traverse/],
    'Aggregate': [/^Sum/, /^Count/, /^Aggregate/, /^Total/, /^Collect/]
};

const PRIMITIVE_TYPES = new Set(['int', 'float', 'double', 'string', 'bool', 'void', 'byte',
    'short', 'long', 'char', 'decimal', 'object', 'var', 'dynamic', 'uint', 'ulong', 'sbyte', 'ushort']);

const UNITY_TYPES = new Set(['MonoBehaviour', 'ScriptableObject', 'GameObject', 'Transform',
    'Component', 'Behaviour', 'Object', 'Coroutine', 'IEnumerator',
    'Vector2', 'Vector3', 'Vector4', 'Quaternion', 'Rect', 'Color', 'Color32',
    'Sprite', 'Image', 'Text', 'Button', 'RectTransform', 'Canvas',
    'AudioSource', 'AudioClip', 'Animator', 'Animation', 'Rigidbody', 'Collider',
    'Rigidbody2D', 'Collider2D', 'BoxCollider2D', 'CircleCollider2D',
    'Camera', 'Light', 'Material', 'Texture', 'Texture2D', 'Mesh', 'Shader',
    'TextMeshProUGUI', 'TextMeshPro', 'TMP_Text', 'TMP_InputField',
    'Toggle', 'Slider', 'Scrollbar', 'ScrollRect', 'Dropdown', 'InputField',
    'CanvasGroup', 'LayoutGroup', 'HorizontalLayoutGroup', 'VerticalLayoutGroup',
    'GridLayoutGroup', 'ContentSizeFitter', 'AspectRatioFitter',
    'SpriteRenderer', 'LineRenderer', 'TrailRenderer', 'ParticleSystem']);

const COLLECTION_TYPES = new Set(['List', 'Dictionary', 'HashSet', 'Queue', 'Stack',
    'Array', 'IList', 'IDictionary', 'IEnumerable', 'ICollection',
    'ConcurrentDictionary', 'LinkedList', 'SortedList', 'SortedDictionary',
    'ObservableCollection', 'ReadOnlyCollection']);

const SYSTEM_TYPES = new Set(['Action', 'Func', 'Task', 'CancellationToken', 'Exception',
    'Type', 'Attribute', 'EventArgs', 'StringBuilder', 'Regex',
    'TimeSpan', 'DateTime', 'Guid', 'Random', 'Math', 'Mathf',
    'Debug', 'PlayerPrefs', 'JsonUtility', 'Resources', 'Application',
    'SceneManager', 'Screen', 'Time', 'Input', 'Physics', 'Physics2D']);

// Recipe templates based on Role + Layer
const RECIPE_TEMPLATES = {
    'Manager_Core': {
        category: 'singleton_manager',
        init_order: 'early',
        lifecycle: 'persistent',
        typical_usage: 'DontDestroyOnLoad 싱글톤. 게임 전체에서 하나만 존재. Awake에서 초기화.',
        do_not: [
            'Update에서 무거운 로직 실행 금지',
            '다른 Manager의 Awake 순서에 의존 금지 — Init 패턴 사용',
            'static 필드로 데이터 보관 금지 — Instance 통해 접근'
        ]
    },
    'Manager_Domain': {
        category: 'domain_manager',
        init_order: 'normal',
        lifecycle: 'scene_bound',
        typical_usage: '특정 도메인(전투, 인벤토리 등) 총괄 관리. 씬 단위로 존재 가능.',
        do_not: [
            'Core Manager와 순환 참조 금지',
            '직접 UI 조작 금지 — 이벤트로 통신',
            'Find/FindObjectOfType 사용 금지'
        ]
    },
    'Controller': {
        category: 'entity_controller',
        init_order: 'normal',
        lifecycle: 'scene_bound',
        typical_usage: '개별 게임 오브젝트 제어. 입력 처리, 상태 전환.',
        do_not: [
            '다른 Controller 직접 참조 금지 — Manager 통해 접근',
            'Manager 역할 겸하지 말 것',
            'new GameObject 런타임 생성 금지'
        ]
    },
    'Pool': {
        category: 'object_pool',
        init_order: 'early',
        lifecycle: 'persistent',
        typical_usage: '반복 생성/파괴 오브젝트 풀링. Awake에서 Pre-warm. Get/Return 패턴.',
        do_not: [
            'Update에서 Instantiate 금지',
            'Return 없이 Destroy 금지',
            'Pool 크기 0으로 시작 금지 — 최소 initialCount 설정'
        ]
    },
    'View': {
        category: 'ui_view',
        init_order: 'late',
        lifecycle: 'scene_bound',
        typical_usage: 'UI 페이지/팝업. SerializeField로 UI 요소 참조. 이벤트로 데이터 수신.',
        do_not: [
            '코드에서 UI 오브젝트 동적 생성 금지 — 프리팹 사용',
            'Manager 로직 포함 금지',
            'Find로 UI 요소 탐색 금지 — SerializeField 사용'
        ]
    },
    'Factory': {
        category: 'object_factory',
        init_order: 'normal',
        lifecycle: 'scene_bound',
        typical_usage: '오브젝트 생성 담당. Prefab 로드 + Instantiate 또는 Pool에서 Get.',
        do_not: [
            '생성 로직 외의 비즈니스 로직 포함 금지',
            'new GameObject + AddComponent 금지 — 프리팹 기반',
            '생성된 오브젝트의 생명주기 관리 금지 — Manager 역할'
        ]
    },
    'Config': {
        category: 'data_config',
        init_order: 'early',
        lifecycle: 'persistent',
        typical_usage: 'ScriptableObject 또는 static 설정값. Inspector에서 편집.',
        do_not: [
            '런타임에 값 변경 금지 (readonly)',
            '로직 포함 금지 — 데이터만',
            'MonoBehaviour 상속 금지 — ScriptableObject 사용'
        ]
    },
    'Data': {
        category: 'data_model',
        init_order: 'none',
        lifecycle: 'transient',
        typical_usage: '데이터 컨테이너. 직렬화/역직렬화 대상. 로직 없음.',
        do_not: [
            '비즈니스 로직 포함 금지',
            'MonoBehaviour 상속 금지',
            'Unity API 호출 금지'
        ]
    },
    'State': {
        category: 'state_machine',
        init_order: 'normal',
        lifecycle: 'scene_bound',
        typical_usage: 'FSM 상태 정의. Enter/Exit/Update 패턴. Controller가 전환.',
        do_not: [
            '다른 State 직접 참조 금지 — StateMachine 통해 전환',
            'State 안에서 씬 전환 금지',
            '전역 상태 변경 금지'
        ]
    },
    'Handler': {
        category: 'event_handler',
        init_order: 'normal',
        lifecycle: 'scene_bound',
        typical_usage: '이벤트 수신 및 처리. 구독/해제 쌍 필수.',
        do_not: [
            'OnEnable에서 구독, OnDisable에서 해제 필수',
            'Handler에서 다른 이벤트 발행 시 무한루프 주의',
            '무거운 처리는 코루틴으로 분산'
        ]
    },
    'Service': {
        category: 'external_service',
        init_order: 'early',
        lifecycle: 'persistent',
        typical_usage: '외부 API, 서버 통신, SDK 연동. 비동기 패턴(async/await, 코루틴).',
        do_not: [
            '동기 블로킹 호출 금지',
            'UI 직접 조작 금지 — 콜백/이벤트로 결과 전달',
            'API 키/시크릿 하드코딩 금지'
        ]
    },
    '_default': {
        category: 'component',
        init_order: 'normal',
        lifecycle: 'scene_bound',
        typical_usage: '일반 컴포넌트.',
        do_not: []
    }
};

// ============================================================
// Parser Class
// ============================================================

class CSharpParser {
    constructor(defaultGenre = 'Generic', projectName = '') {
        this.defaultGenre = defaultGenre;
        this.projectName = projectName;
    }

    parseFile(filePath, relativePath, fullContent = null) {
        let content;
        try {
            content = fullContent || fs.readFileSync(filePath, 'utf-8');
            if (content.charCodeAt(0) === 0xFEFF) {
                content = content.slice(1);
            }
        } catch (e) {
            console.error(`Error reading ${filePath}: ${e.message}`);
            return null;
        }

        const fileName = path.basename(filePath);
        const fileId = path.parse(fileName).name;

        const usings = this.extractUsings(content);
        const namespace = this.extractNamespace(content);
        const classes = this.extractClasses(content);

        if (classes.length === 0) {
            return null;
        }

        const mainClass = classes[0];

        const role = this.determineRoleAdvanced(fileId, mainClass);
        const layer = this.determineLayerAdvanced(fileId, relativePath, mainClass);
        const genre = this.determineGenre(fileId, relativePath, content, layer);
        const system = this.determineSystem(relativePath, fileId);
        const uses = this.extractUses(content, fileId);
        const { provides, requires } = this.extractContractAdvanced(classes, content);

        const allMethods = classes.reduce((acc, cls) => acc.concat(cls.methods), []);
        const tags = this.classifyClassTags(allMethods);

        // === NEW v4: Enriched fields ===
        const unity_config = this.extractUnityConfig(mainClass, content);
        const integration = this.extractIntegration(content, fileId);
        const recipe = this.generateRecipe(role, layer, unity_config, mainClass);

        return {
            fileId,
            filePath: relativePath,
            namespace,
            layer,
            genre,
            role,
            system,
            project: this.projectName,
            score: 0.4,
            usings,
            classes,
            provides,
            requires,
            tags,
            uses,
            usedBy: [],
            // v4 enriched fields
            unity_config,
            integration,
            recipe
        };
    }

    // ============================================================
    // v4 NEW: Unity Configuration Extraction
    // ============================================================

    extractUnityConfig(mainClass, content) {
        const config = {
            is_singleton: false,
            is_mono: false,
            is_scriptable: false,
            is_static_class: false,
            init_timing: 'None',
            dont_destroy: false,
            requires_prefab: false,
            coroutine_heavy: false,
            serialized_fields: [],
            lifecycle_methods: [],
            data_structures: []
        };

        if (!mainClass) return config;

        // Singleton check
        if (mainClass.baseClass) {
            const base = mainClass.baseClass.toLowerCase();
            config.is_singleton = base.includes('singleton');
            config.is_mono = base.includes('monobehaviour') || config.is_singleton;
            config.is_scriptable = base.includes('scriptableobject');
        }

        config.is_static_class = mainClass.isStatic;

        // Init timing — which lifecycle method has init code
        const methodNames = mainClass.methods.map(m => m.methodName);
        if (methodNames.includes('Awake')) config.init_timing = 'Awake';
        else if (methodNames.includes('Start')) config.init_timing = 'Start';
        else if (methodNames.includes('OnEnable')) config.init_timing = 'OnEnable';

        // DontDestroyOnLoad
        config.dont_destroy = /DontDestroyOnLoad/i.test(content) || config.is_singleton;

        // Lifecycle methods used
        config.lifecycle_methods = methodNames.filter(m => UNITY_LIFECYCLE.has(m));

        // SerializeField extraction
        for (const cls of [mainClass]) {
            for (const field of cls.fields) {
                if (field.hasSerializeField) {
                    config.serialized_fields.push({
                        name: field.fieldName,
                        type: field.fieldType,
                        is_prefab: /GameObject|Transform|Prefab/i.test(field.fieldType),
                        is_ui: /Image|Text|Button|Slider|Toggle|Canvas|RectTransform|TMP_|TextMesh/i.test(field.fieldType)
                    });
                }
            }
        }

        // Requires prefab (has SerializeField for GameObject/Transform)
        config.requires_prefab = config.serialized_fields.some(f => f.is_prefab);

        // Coroutine heavy (3+ coroutine methods)
        const coroutineCount = mainClass.methods.filter(m => m.isCoroutine || m.isAsync).length;
        config.coroutine_heavy = coroutineCount >= 3;

        // Data structures used
        const dsPatterns = [
            { name: 'List', pattern: /List</ },
            { name: 'Dictionary', pattern: /Dictionary</ },
            { name: 'Queue', pattern: /Queue</ },
            { name: 'Stack', pattern: /Stack</ },
            { name: 'HashSet', pattern: /HashSet</ },
            { name: 'Array', pattern: /\w+\[\]/ },
            { name: 'LinkedList', pattern: /LinkedList</ },
            { name: 'SortedList', pattern: /SortedList</ },
        ];
        for (const ds of dsPatterns) {
            if (ds.pattern.test(content)) {
                config.data_structures.push(ds.name);
            }
        }

        return config;
    }

    // ============================================================
    // v4 NEW: Integration Map Extraction
    // ============================================================

    extractIntegration(content, fileId) {
        const integration = {
            singleton_access: [],     // OtherManager.Instance calls
            get_component: [],        // GetComponent<T>
            event_subscribe: [],      // += handler
            event_publish: [],        // ?.Invoke or Invoke
            instantiate_calls: [],    // Instantiate patterns
            resource_load: [],        // Resources.Load
            addressable_load: [],     // Addressables
            pool_usage: [],           // ObjectPool.Get/Return
            coroutine_calls: [],      // StartCoroutine
            scene_operations: [],     // SceneManager operations
            find_calls: [],           // Find/FindObjectOfType (anti-pattern detection)
            new_gameobject: [],       // new GameObject (anti-pattern detection)
        };

        // Singleton.Instance access
        const singletonPattern = /(\w+)\.Instance(?:\.(\w+))?/g;
        let match;
        while ((match = singletonPattern.exec(content)) !== null) {
            if (match[1] !== fileId) {
                const entry = { target: match[1] };
                if (match[2]) entry.method = match[2];
                if (!integration.singleton_access.find(e => e.target === entry.target && e.method === entry.method)) {
                    integration.singleton_access.push(entry);
                }
            }
        }

        // GetComponent<T>
        const getCompPattern = /GetComponent(?:InChildren|InParent)?<(\w+)>/g;
        while ((match = getCompPattern.exec(content)) !== null) {
            if (!integration.get_component.includes(match[1])) {
                integration.get_component.push(match[1]);
            }
        }

        // Event subscribe (+= / -=)
        const eventSubPattern = /(\w+)\s*\+\=\s*(\w+)/g;
        while ((match = eventSubPattern.exec(content)) !== null) {
            integration.event_subscribe.push({ event: match[1], handler: match[2] });
        }

        // Event publish (?.Invoke / .Invoke)
        const eventPubPattern = /(\w+)\?\s*\.?\s*Invoke\s*\(/g;
        while ((match = eventPubPattern.exec(content)) !== null) {
            if (!integration.event_publish.includes(match[1])) {
                integration.event_publish.push(match[1]);
            }
        }
        const eventPubPattern2 = /(\w+)\.Invoke\s*\(/g;
        while ((match = eventPubPattern2.exec(content)) !== null) {
            if (!integration.event_publish.includes(match[1]) &&
                !['Action', 'Func', 'UnityEvent'].includes(match[1])) {
                integration.event_publish.push(match[1]);
            }
        }

        // Instantiate
        const instPattern = /Instantiate\s*(?:<(\w+)>)?\s*\(([^)]*)\)/g;
        while ((match = instPattern.exec(content)) !== null) {
            integration.instantiate_calls.push({
                type: match[1] || 'GameObject',
                args_preview: match[2].slice(0, 60)
            });
        }

        // Resources.Load
        const resPattern = /Resources\.Load(?:<(\w+)>)?\s*\(\s*"([^"]+)"/g;
        while ((match = resPattern.exec(content)) !== null) {
            integration.resource_load.push({ type: match[1] || 'Object', path: match[2] });
        }

        // Addressables
        const addrPattern = /Addressables\.\w+Async\s*(?:<(\w+)>)?\s*\(\s*"([^"]+)"/g;
        while ((match = addrPattern.exec(content)) !== null) {
            integration.addressable_load.push({ type: match[1] || 'Object', key: match[2] });
        }

        // ObjectPool usage
        const poolGetPattern = /(?:ObjectPool|Pool)\w*\.(?:Instance\.)?(?:Get|Spawn)\s*(?:<(\w+)>)?\s*\(/g;
        while ((match = poolGetPattern.exec(content)) !== null) {
            integration.pool_usage.push({ action: 'Get', type: match[1] || 'unknown' });
        }
        const poolReturnPattern = /(?:ObjectPool|Pool)\w*\.(?:Instance\.)?(?:Return|Despawn|Release)\s*\(/g;
        while ((match = poolReturnPattern.exec(content)) !== null) {
            integration.pool_usage.push({ action: 'Return' });
        }

        // StartCoroutine
        const coroPattern = /StartCoroutine\s*\(\s*(\w+)\s*\(/g;
        while ((match = coroPattern.exec(content)) !== null) {
            if (!integration.coroutine_calls.includes(match[1])) {
                integration.coroutine_calls.push(match[1]);
            }
        }

        // SceneManager operations
        const scenePattern = /SceneManager\.\s*(\w+)\s*\(/g;
        while ((match = scenePattern.exec(content)) !== null) {
            if (!integration.scene_operations.includes(match[1])) {
                integration.scene_operations.push(match[1]);
            }
        }

        // Anti-pattern: Find calls
        const findPattern = /(?:GameObject\.)?Find(?:ObjectOfType|WithTag|ObjectsOfType)?\s*(?:<(\w+)>)?\s*\(/g;
        while ((match = findPattern.exec(content)) !== null) {
            integration.find_calls.push(match[1] || 'unknown');
        }

        // Anti-pattern: new GameObject
        const newGOPattern = /new\s+GameObject\s*\(/g;
        let newGOCount = 0;
        while (newGOPattern.exec(content) !== null) newGOCount++;
        if (newGOCount > 0) {
            integration.new_gameobject.push({ count: newGOCount });
        }

        return integration;
    }

    // ============================================================
    // v4 NEW: Recipe Generation
    // ============================================================

    generateRecipe(role, layer, unityConfig, mainClass) {
        // Look up recipe template
        const key = `${role}_${layer}`;
        let template = RECIPE_TEMPLATES[key] || RECIPE_TEMPLATES[role] || RECIPE_TEMPLATES['_default'];

        const recipe = {
            category: template.category,
            init_order: template.init_order,
            lifecycle: template.lifecycle,
            typical_usage: template.typical_usage,
            do_not: [...template.do_not]
        };

        // Adjust based on unity_config
        if (unityConfig.is_singleton) {
            recipe.lifecycle = 'persistent';
            recipe.init_order = 'early';
        }
        if (unityConfig.dont_destroy && !unityConfig.is_singleton) {
            recipe.lifecycle = 'persistent';
        }
        if (unityConfig.coroutine_heavy) {
            recipe.do_not.push('코루틴 과다 — StopAllCoroutines 누락 시 메모리 리크');
        }

        // Anti-pattern warnings from integration
        if (unityConfig.serialized_fields.some(f => f.is_ui)) {
            recipe.do_not.push('UI 참조는 SerializeField 유지 — Find로 재탐색 금지');
        }

        return recipe;
    }

    // ============================================================
    // Existing extraction methods (unchanged)
    // ============================================================

    extractUsings(content) {
        const pattern = /using\s+([\w.]+)\s*;/g;
        const usings = [];
        let match;
        while ((match = pattern.exec(content)) !== null) {
            usings.push(match[1]);
        }
        return usings;
    }

    extractNamespace(content) {
        const pattern = /namespace\s+([\w.]+)/;
        const match = content.match(pattern);
        return match ? match[1] : '';
    }

    extractClasses(content) {
        const classes = [];
        const pattern = /(public|private|protected|internal)?\s*(partial)?\s*(abstract)?\s*(static)?\s*(class|struct|interface|enum)\s+(\w+)(?:<[^>]+>)?(?:\s*:\s*([^{]+))?/g;

        let match;
        while ((match = pattern.exec(content)) !== null) {
            const access = match[1] || 'internal';
            const isPartial = !!match[2];
            const isAbstract = !!match[3];
            const isStatic = !!match[4];
            const classType = match[5];
            const className = match[6];
            const inheritance = match[7];

            let baseClass = null;
            const interfaces = [];

            if (inheritance) {
                const parts = inheritance.split(',').map(p => p.trim());
                for (let i = 0; i < parts.length; i++) {
                    const part = parts[i].split('<')[0].trim();
                    const fullPart = parts[i].trim();
                    if (i === 0 && !part.startsWith('I')) {
                        baseClass = fullPart;
                    } else if (part.startsWith('I') && part.length > 1 && part[1] === part[1].toUpperCase()) {
                        interfaces.push(fullPart);
                    } else if (i === 0) {
                        baseClass = fullPart;
                    }
                }
            }

            const methods = this.extractMethods(content, className);
            const fields = this.extractFields(content, className);
            const properties = this.extractProperties(content, className);

            classes.push({
                className,
                classType,
                accessModifier: access,
                isPartial,
                isAbstract,
                isStatic,
                baseClass,
                interfaces,
                fields,
                properties,
                methods
            });
        }

        return classes;
    }

    extractMethods(content, className) {
        const methods = [];
        const pattern = /(public|private|protected|internal)\s+(static\s+)?(virtual\s+)?(override\s+)?(async\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)/g;

        let match;
        while ((match = pattern.exec(content)) !== null) {
            const access = match[1];
            const isStatic = !!match[2];
            const isVirtual = !!match[3];
            const isOverride = !!match[4];
            const isAsync = !!match[5];
            const returnType = match[6].trim();
            const methodName = match[7];
            const paramsStr = match[8];

            if (['get', 'set', 'value'].includes(methodName)) continue;

            const parameters = [];
            if (paramsStr.trim()) {
                for (const param of paramsStr.split(',')) {
                    const trimmed = param.trim();
                    if (trimmed) {
                        const parts = trimmed.split(/\s+/);
                        if (parts.length >= 2) {
                            parameters.push({
                                paramType: parts.slice(0, -1).join(' '),
                                paramName: parts[parts.length - 1]
                            });
                        }
                    }
                }
            }

            const signature = `${returnType} ${methodName}(${paramsStr})`;
            const isCoroutine = returnType === 'IEnumerator';

            const { majorTag, minorTag } = this.classifyMethodTag(methodName);

            methods.push({
                methodName,
                accessModifier: access,
                returnType,
                parameters,
                signature,
                isStatic,
                isVirtual,
                isOverride,
                isAsync,
                isCoroutine,
                majorTag,
                minorTag
            });
        }

        return methods;
    }

    extractFields(content, className) {
        const fields = [];

        const classPattern = new RegExp(`(class|struct)\\s+${className}[^{]*\\{`);
        const classMatch = content.match(classPattern);
        if (!classMatch) return fields;

        const start = classMatch.index + classMatch[0].length;
        let depth = 1;
        let i = start;

        while (i < content.length && depth > 0) {
            if (content[i] === '{') depth++;
            else if (content[i] === '}') depth--;
            i++;
        }

        const classBody = content.slice(start, i);

        const fieldPattern = /(\[SerializeField\]\s*|\[Inject\]\s*)?(public|private|protected|internal)\s+(static\s+)?(readonly\s+)?(const\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*(?:=\s*([^;]+))?\s*;/g;

        let match;
        while ((match = fieldPattern.exec(classBody)) !== null) {
            const hasAttribute = !!match[1];
            const attributeType = match[1] ? (match[1].includes('Inject') ? 'Inject' : 'SerializeField') : null;
            const access = match[2];
            const isStatic = !!match[3];
            const isReadonly = !!match[4];
            const isConst = !!match[5];
            const fieldType = match[6].trim();
            const fieldName = match[7];
            const initialValue = match[8];

            if (['return', 'if', 'for', 'while', 'foreach', 'new', 'throw'].includes(fieldType)) continue;

            fields.push({
                fieldName,
                fieldType,
                accessModifier: access,
                isStatic,
                isReadonly,
                isConst,
                hasSerializeField: attributeType === 'SerializeField',
                hasInject: attributeType === 'Inject',
                initialValue: initialValue ? initialValue.trim() : null
            });
        }

        return fields;
    }

    extractProperties(content, className) {
        const properties = [];
        const pattern = /(public|private|protected|internal)\s+(static\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*\{\s*(get;?)?\s*(set;?)?\s*\}/g;

        let match;
        while ((match = pattern.exec(content)) !== null) {
            const access = match[1];
            const propType = match[3].trim();
            const propName = match[4];
            const hasGetter = !!match[5];
            const hasSetter = !!match[6];

            properties.push({
                propertyName: propName,
                propertyType: propType,
                accessModifier: access,
                hasGetter,
                hasSetter
            });
        }

        return properties;
    }

    extractUses(content, fileId) {
        const uses = new Set();

        const typePattern = /(?:new\s+|:\s*|<|,\s*)(\w+)(?:<[^>]+>)?(?:\s*[>\(\[\{,]|$)/g;
        let match;
        while ((match = typePattern.exec(content)) !== null) {
            const typeName = match[1];
            if (this.isValidDependency(typeName, fileId)) {
                uses.add(typeName);
            }
        }

        const singletonPattern = /(\w+)\.Instance/g;
        while ((match = singletonPattern.exec(content)) !== null) {
            const typeName = match[1];
            if (this.isValidDependency(typeName, fileId)) {
                uses.add(typeName);
            }
        }

        const staticPattern = /(\w+)\.(\w+)\s*\(/g;
        while ((match = staticPattern.exec(content)) !== null) {
            const typeName = match[1];
            const methodName = match[2];
            if (this.isValidDependency(typeName, fileId) && !UNITY_LIFECYCLE.has(methodName)) {
                uses.add(typeName);
            }
        }

        return Array.from(uses).sort();
    }

    isValidDependency(typeName, fileId) {
        if (!typeName || typeName.length < 2) return false;
        if (typeName === fileId) return false;
        if (PRIMITIVE_TYPES.has(typeName.toLowerCase())) return false;
        if (UNITY_TYPES.has(typeName)) return false;
        if (COLLECTION_TYPES.has(typeName)) return false;
        if (SYSTEM_TYPES.has(typeName)) return false;
        if (UNITY_LIFECYCLE.has(typeName)) return false;
        if (COMMON_METHODS.has(typeName)) return false;
        if (typeName[0] !== typeName[0].toUpperCase()) return false;
        return true;
    }

    // ============================================================
    // Contract Extraction
    // ============================================================

    extractContractAdvanced(classes, content) {
        const provides = [];
        const requiresSet = new Set();

        for (const cls of classes) {
            for (const method of cls.methods) {
                if (method.accessModifier === 'public') {
                    provides.push(method.signature);
                }
            }

            for (const prop of cls.properties) {
                if (prop.accessModifier === 'public' && prop.hasGetter) {
                    provides.push(`${prop.propertyType} ${prop.propertyName} { get; }`);
                }
            }

            for (const iface of cls.interfaces) {
                const cleanIface = this.extractTypeName(iface);
                if (this.isValidRequires(cleanIface)) requiresSet.add(cleanIface);
                for (const arg of this.extractGenericArgs(iface)) {
                    if (this.isValidRequires(arg)) requiresSet.add(arg);
                }
            }

            if (cls.baseClass) {
                const baseName = this.extractTypeName(cls.baseClass);
                if (this.isValidRequires(baseName) && !UNITY_TYPES.has(baseName)) {
                    requiresSet.add(baseName);
                }
            }

            for (const field of cls.fields) {
                if (field.hasSerializeField || field.hasInject) {
                    const typeName = this.extractTypeName(field.fieldType);
                    if (this.isValidRequires(typeName)) requiresSet.add(typeName);
                    for (const arg of this.extractGenericArgs(field.fieldType)) {
                        if (this.isValidRequires(arg)) requiresSet.add(arg);
                    }
                }
            }

            const initMethods = cls.methods.filter(m =>
                ['Init', 'Initialize', 'Setup', 'Configure', 'SetMessageController', 'Construct'].includes(m.methodName)
            );
            for (const method of initMethods) {
                for (const param of method.parameters) {
                    const typeName = this.extractTypeName(param.paramType);
                    if (this.isValidRequires(typeName)) requiresSet.add(typeName);
                    for (const arg of this.extractGenericArgs(param.paramType)) {
                        if (this.isValidRequires(arg)) requiresSet.add(arg);
                    }
                }
            }

            for (const field of cls.fields) {
                if (field.accessModifier === 'public' || field.accessModifier === 'protected') {
                    const typeName = this.extractTypeName(field.fieldType);
                    if (this.isValidRequires(typeName)) requiresSet.add(typeName);
                }
            }
        }

        const getComponentPattern = /GetComponent<(\w+)>/g;
        let match;
        while ((match = getComponentPattern.exec(content)) !== null) {
            if (this.isValidRequires(match[1])) requiresSet.add(match[1]);
        }

        return {
            provides: provides.slice(0, 15),
            requires: Array.from(requiresSet).sort().slice(0, 15)
        };
    }

    extractTypeName(fullType) {
        if (!fullType) return '';
        return fullType.split('<')[0].split('[')[0].trim();
    }

    extractGenericArgs(fullType) {
        const args = [];
        const match = fullType.match(/<([^>]+)>/);
        if (match) {
            const parts = match[1].split(',').map(p => p.trim());
            for (const part of parts) {
                const typeName = this.extractTypeName(part);
                if (typeName && !PRIMITIVE_TYPES.has(typeName.toLowerCase())) args.push(typeName);
            }
        }
        return args;
    }

    isValidRequires(typeName) {
        if (!typeName || typeName.length < 2) return false;
        if (PRIMITIVE_TYPES.has(typeName.toLowerCase())) return false;
        if (UNITY_TYPES.has(typeName)) return false;
        if (COLLECTION_TYPES.has(typeName)) return false;
        if (SYSTEM_TYPES.has(typeName)) return false;
        if (typeName[0] !== typeName[0].toUpperCase()) return false;
        return true;
    }

    // ============================================================
    // Tag Classification
    // ============================================================

    classifyMethodTag(methodName) {
        if (UNITY_LIFECYCLE.has(methodName) || COMMON_METHODS.has(methodName)) {
            return { majorTag: null, minorTag: null };
        }

        let majorTag = null;
        let minorTag = null;

        for (const [tag, patterns] of Object.entries(MAJOR_TAG_PATTERNS)) {
            if (patterns.some(p => p.test(methodName))) { majorTag = tag; break; }
        }

        for (const [tag, patterns] of Object.entries(MINOR_TAG_PATTERNS)) {
            if (patterns.some(p => p.test(methodName))) { minorTag = tag; break; }
        }

        return { majorTag, minorTag };
    }

    classifyClassTags(methods) {
        const majorCounts = {};
        const minorCounts = {};

        for (const method of methods) {
            const { majorTag, minorTag } = this.classifyMethodTag(method.methodName);
            if (majorTag) majorCounts[majorTag] = (majorCounts[majorTag] || 0) + 1;
            if (minorTag) minorCounts[minorTag] = (minorCounts[minorTag] || 0) + 1;
        }

        const majorTags = Object.entries(majorCounts)
            .sort((a, b) => b[1] - a[1]).slice(0, 3).map(([tag]) => tag);

        const minorTags = Object.entries(minorCounts)
            .sort((a, b) => b[1] - a[1]).slice(0, 3).map(([tag]) => tag);

        return { major: majorTags, minor: minorTags };
    }

    // ============================================================
    // Role / Layer / Genre / System Classification
    // ============================================================

    determineRoleAdvanced(fileId, classInfo) {
        if (!classInfo) return 'Component';

        if (classInfo.classType === 'interface') return 'Interface';
        if (classInfo.classType === 'enum') return 'Enum';
        if (classInfo.classType === 'struct' && /Msg$|Message$/.test(classInfo.className)) return 'Message';
        if (classInfo.isAbstract) return 'Base';

        if (classInfo.baseClass) {
            const baseName = classInfo.baseClass.split('<')[0].trim();
            for (const [role, patterns] of Object.entries(ROLE_BASE_CLASS)) {
                for (const pattern of patterns) {
                    if (baseName.includes(pattern)) return role;
                }
            }
        }

        for (const iface of classInfo.interfaces) {
            const ifaceName = iface.split('<')[0].trim();
            for (const [role, patterns] of Object.entries(ROLE_INTERFACE)) {
                for (const pattern of patterns) {
                    if (ifaceName.includes(pattern)) return role;
                }
            }
        }

        if (classInfo.fields.length > 0) {
            const allConst = classInfo.fields.every(f => f.isConst || f.isStatic);
            if (allConst && classInfo.fields.length >= 3) return 'Config';
        }

        const publicFields = classInfo.fields.filter(f => f.accessModifier === 'public').length;
        const publicMethods = classInfo.methods.filter(m => m.accessModifier === 'public').length;
        if (publicFields > publicMethods && publicFields >= 3) return 'Model';

        for (const [role, patterns] of Object.entries(ROLE_NAME_PATTERNS)) {
            for (const pattern of patterns) {
                if (pattern.test(fileId) || pattern.test(classInfo.className)) return role;
            }
        }

        return 'Component';
    }

    determineLayerAdvanced(fileId, filePath, classInfo) {
        const pathLower = filePath.toLowerCase();
        const fileLower = fileId.toLowerCase();
        const combined = fileLower + ' ' + pathLower;

        for (const keyword of DOMAIN_FORCE_KEYWORDS) {
            if (combined.includes(keyword.toLowerCase())) return 'Domain';
        }

        for (const keyword of LAYER_KEYWORDS['Game']) {
            if (fileLower.includes(keyword.toLowerCase())) return 'Game';
        }

        if (classInfo && classInfo.baseClass) {
            const base = classInfo.baseClass.toLowerCase();
            if (['page', 'popup', 'win', 'panel', 'uibase', 'windowbase'].some(kw => base.includes(kw))) return 'Game';
        }

        for (const keyword of LAYER_KEYWORDS['Core']) {
            if (fileLower.includes(keyword.toLowerCase()) || pathLower.includes(keyword.toLowerCase())) return 'Core';
        }

        if (classInfo && classInfo.baseClass) {
            const base = classInfo.baseClass.toLowerCase();
            if (base.includes('singleton')) return 'Core';
        }

        return 'Domain';
    }

    determineGenre(fileId, filePath, content, layer) {
        const combined = (fileId + ' ' + filePath + ' ' + content.slice(0, 1000)).toLowerCase();

        const scores = {};
        for (const [genre, keywords] of Object.entries(GENRE_KEYWORDS)) {
            const score = keywords.filter(kw => combined.includes(kw.toLowerCase())).length;
            if (score > 0) scores[genre] = score;
        }

        if (Object.keys(scores).length > 0) {
            const detected = Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0];
            return detected.charAt(0).toUpperCase() + detected.slice(1).toLowerCase();
        }

        if (layer === 'Core') return 'Generic';

        return this.defaultGenre.charAt(0).toUpperCase() + this.defaultGenre.slice(1).toLowerCase();
    }

    determineSystem(filePath, fileId) {
        const parts = filePath.split(/[/\\]/);
        const skip = new Set(['Scripts', 'Assets', 'Project', 'PPM', 'IdleMoney', 'src', 'Source']);

        for (const part of parts) {
            if (!skip.has(part) && !part.endsWith('.cs')) return part;
        }

        return fileId;
    }
}

// ============================================================
// v4 NEW: Cross-file Integration Resolver
// ============================================================

function resolveUsedBy(allFiles) {
    const usesMap = new Map();

    // Build forward map
    for (const file of allFiles) {
        usesMap.set(file.fileId, file.uses || []);
    }

    // Build reverse map
    for (const file of allFiles) {
        file.usedBy = [];
    }

    const fileMap = new Map(allFiles.map(f => [f.fileId, f]));

    for (const file of allFiles) {
        for (const dep of (file.uses || [])) {
            const target = fileMap.get(dep);
            if (target && !target.usedBy.includes(file.fileId)) {
                target.usedBy.push(file.fileId);
            }
        }
    }

    return allFiles;
}

// ============================================================
// Database Manager (v4: Local + MongoDB dual write)
// ============================================================

class DatabaseManager {
    constructor(dbPath, mongoEnabled = false) {
        this.dbPath = dbPath;
        this.mongoEnabled = mongoEnabled;
        this.mongoClient = null;
        this.indices = {};
        this.allFiles = [];
        this.loadExistingIndices();
    }

    loadExistingIndices() {
        const basePath = path.join(this.dbPath, 'base');
        if (!fs.existsSync(basePath)) return;

        for (const genre of fs.readdirSync(basePath)) {
            const genrePath = path.join(basePath, genre);
            if (!fs.statSync(genrePath).isDirectory()) continue;

            for (const layer of fs.readdirSync(genrePath)) {
                const layerPath = path.join(genrePath, layer);
                if (!fs.statSync(layerPath).isDirectory()) continue;

                const indexPath = path.join(layerPath, 'index.json');
                if (fs.existsSync(indexPath)) {
                    const key = `${genre}_${layer}`;
                    try {
                        this.indices[key] = JSON.parse(fs.readFileSync(indexPath, 'utf-8'));
                    } catch (e) {
                        this.indices[key] = [];
                    }
                }
            }
        }
    }

    addFile(fileInfo) {
        // Limit stored data for large files to prevent OOM
        for (const cls of fileInfo.classes) {
            if (cls.methods.length > 80) cls.methods = cls.methods.slice(0, 80);
            if (cls.fields.length > 60) cls.fields = cls.fields.slice(0, 60);
            if (cls.properties.length > 40) cls.properties = cls.properties.slice(0, 40);
        }
        if (fileInfo.uses && fileInfo.uses.length > 50) fileInfo.uses = fileInfo.uses.slice(0, 50);
        if (fileInfo.provides && fileInfo.provides.length > 20) fileInfo.provides = fileInfo.provides.slice(0, 20);

        this.allFiles.push(fileInfo);

        const genre = fileInfo.genre.toLowerCase();
        const layer = fileInfo.layer.toLowerCase();

        const genrePath = path.join(this.dbPath, 'base', genre, layer);
        const filesPath = path.join(genrePath, 'files');

        if (!fs.existsSync(filesPath)) {
            fs.mkdirSync(filesPath, { recursive: true });
        }

        const filePath = path.join(filesPath, `${fileInfo.fileId}.json`);
        fs.writeFileSync(filePath, JSON.stringify(fileInfo, null, 2), 'utf-8');

        const key = `${genre}_${layer}`;
        if (!this.indices[key]) this.indices[key] = [];

        this.indices[key] = this.indices[key].filter(e => e.fileId !== fileInfo.fileId);

        this.indices[key].push({
            fileId: fileInfo.fileId,
            layer: fileInfo.layer,
            genre: fileInfo.genre,
            role: fileInfo.role,
            system: fileInfo.system,
            project: fileInfo.project,
            score: fileInfo.score,
            provides: fileInfo.provides.slice(0, 5),
            requires: fileInfo.requires.slice(0, 5),
            tags: fileInfo.tags,
            unity_config: {
                is_singleton: fileInfo.unity_config.is_singleton,
                init_timing: fileInfo.unity_config.init_timing,
                dont_destroy: fileInfo.unity_config.dont_destroy,
                lifecycle_methods: fileInfo.unity_config.lifecycle_methods
            },
            recipe_category: fileInfo.recipe.category
        });
    }

    saveIndices() {
        for (const [key, entries] of Object.entries(this.indices)) {
            const [genre, layer] = key.split('_');
            const indexPath = path.join(this.dbPath, 'base', genre, layer, 'index.json');

            const dir = path.dirname(indexPath);
            if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

            fs.writeFileSync(indexPath, JSON.stringify(entries, null, 2), 'utf-8');
        }
    }

    async connectMongo() {
        if (!this.mongoEnabled) return;
        try {
            const dbClient = require('./lib/db-client');
            this.mongoClient = dbClient;
            await dbClient.connect();
            console.log('MongoDB connected for dual write');
        } catch (e) {
            console.warn(`MongoDB connection failed: ${e.message} — local-only mode`);
            this.mongoEnabled = false;
        }
    }

    async syncToMongo() {
        if (!this.mongoEnabled || !this.mongoClient) return;

        console.log(`\nSyncing ${this.allFiles.length} files to MongoDB...`);
        let synced = 0;

        for (const file of this.allFiles) {
            try {
                await this.mongoClient.upsertCode(file);
                synced++;
                if (synced % 100 === 0) console.log(`  Synced: ${synced}/${this.allFiles.length}`);
            } catch (e) {
                console.error(`  MongoDB upsert failed for ${file.fileId}: ${e.message}`);
            }
        }

        console.log(`MongoDB sync complete: ${synced}/${this.allFiles.length}`);
    }
}

// ============================================================
// File Walker
// ============================================================

function* walkDir(dir) {
    let files;
    try {
        files = fs.readdirSync(dir);
    } catch (e) {
        return;
    }
    for (const file of files) {
        const filePath = path.join(dir, file);
        try {
            const stat = fs.statSync(filePath);
            if (stat.isDirectory()) {
                yield* walkDir(filePath);
            } else {
                yield filePath;
            }
        } catch (e) {
            continue;
        }
    }
}

// ============================================================
// Main
// ============================================================

async function parseProject(sourcePath, genre, dbPath, projectName, mongoEnabled) {
    const parser = new CSharpParser(genre, projectName);
    const db = new DatabaseManager(dbPath, mongoEnabled);

    if (mongoEnabled) {
        await db.connectMongo();
    }

    const stats = {
        total: 0,
        parsed: 0,
        failed: 0,
        skipped_dirs: 0,
        byLayer: {},
        byGenre: {},
        byRole: {},
        byMajorTag: {},
        byRecipeCategory: {},
        anti_patterns: { find_calls: 0, new_gameobject: 0 }
    };

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Parser v4.0 — Enriched Schema`);
    console.log(`${'='.repeat(60)}`);
    console.log(`Source:   ${sourcePath}`);
    console.log(`Project:  ${projectName}`);
    console.log(`Genre:    ${genre}`);
    console.log(`DB Path:  ${dbPath}`);
    console.log(`MongoDB:  ${mongoEnabled ? 'enabled' : 'disabled'}`);
    console.log(`${'='.repeat(60)}\n`);

    const skipDirs = ['Editor', 'Test', 'Tests', 'Plugins', 'ThirdParty', 'TextMesh Pro',
        'DOTween', 'Demigiant', 'Firebase', 'GoogleMobileAds', 'ExternalDependencyManager',
        'PlayServicesResolver', 'AndroidNativePlugin', 'NativeGallery', 'NativeShare'];

    for (const filePath of walkDir(sourcePath)) {
        if (!filePath.endsWith('.cs')) continue;

        const relative = path.relative(sourcePath, filePath);

        if (skipDirs.some(skip => relative.split(path.sep).includes(skip))) {
            stats.skipped_dirs++;
            continue;
        }

        stats.total++;

        const fileInfo = parser.parseFile(filePath, relative);

        if (fileInfo) {
            db.addFile(fileInfo);
            stats.parsed++;

            stats.byLayer[fileInfo.layer] = (stats.byLayer[fileInfo.layer] || 0) + 1;
            stats.byGenre[fileInfo.genre] = (stats.byGenre[fileInfo.genre] || 0) + 1;
            stats.byRole[fileInfo.role] = (stats.byRole[fileInfo.role] || 0) + 1;
            stats.byRecipeCategory[fileInfo.recipe.category] = (stats.byRecipeCategory[fileInfo.recipe.category] || 0) + 1;

            if (fileInfo.tags) {
                for (const tag of fileInfo.tags.major) {
                    stats.byMajorTag[tag] = (stats.byMajorTag[tag] || 0) + 1;
                }
            }

            // Anti-pattern tracking
            if (fileInfo.integration.find_calls.length > 0) stats.anti_patterns.find_calls++;
            if (fileInfo.integration.new_gameobject.length > 0) stats.anti_patterns.new_gameobject++;

            if (stats.parsed % 200 === 0) {
                console.log(`  Parsed: ${stats.parsed} files...`);
            }
        } else {
            stats.failed++;
        }
    }

    // Cross-file integration resolution
    console.log('\nResolving cross-file dependencies...');
    resolveUsedBy(db.allFiles);

    // Re-save with usedBy populated
    for (const file of db.allFiles) {
        const genre_l = file.genre.toLowerCase();
        const layer_l = file.layer.toLowerCase();
        const filesPath = path.join(dbPath, 'base', genre_l, layer_l, 'files');
        const fp = path.join(filesPath, `${file.fileId}.json`);
        fs.writeFileSync(fp, JSON.stringify(file, null, 2), 'utf-8');
    }

    db.saveIndices();

    // MongoDB sync
    if (mongoEnabled) {
        await db.syncToMongo();
        await db.mongoClient.close();
    }

    // Summary
    console.log(`\n${'='.repeat(60)}`);
    console.log(`RESULTS`);
    console.log(`${'='.repeat(60)}`);
    console.log(`Total C# files:  ${stats.total}`);
    console.log(`Parsed:           ${stats.parsed}`);
    console.log(`Failed:           ${stats.failed}`);
    console.log(`Skipped (3rd):    ${stats.skipped_dirs}`);
    console.log(`\nBy Layer:`, JSON.stringify(stats.byLayer, null, 2));
    console.log(`By Genre:`, JSON.stringify(stats.byGenre, null, 2));

    const topRoles = Object.entries(stats.byRole)
        .sort((a, b) => b[1] - a[1]).slice(0, 15)
        .reduce((obj, [k, v]) => { obj[k] = v; return obj; }, {});
    console.log(`By Role (top 15):`, JSON.stringify(topRoles, null, 2));
    console.log(`By Recipe:`, JSON.stringify(stats.byRecipeCategory, null, 2));
    console.log(`By Major Tag:`, JSON.stringify(stats.byMajorTag, null, 2));
    console.log(`\nAnti-patterns detected:`);
    console.log(`  Find() usage:        ${stats.anti_patterns.find_calls} files`);
    console.log(`  new GameObject():    ${stats.anti_patterns.new_gameobject} files`);
    console.log(`${'='.repeat(60)}`);

    return stats;
}

// CLI
const args = process.argv.slice(2);

if (args.length < 2) {
    console.log(`
Usage: node parser.js <source_path> <genre> [options]

Arguments:
  source_path   Unity project Assets/Scripts path
  genre         RPG, Idle, Merge, SLG, Tycoon, Simulation, Puzzle, Casual, Generic

Options:
  --project <name>   Project name (default: folder name)
  --db <path>        Local DB path (default: E:/AI/db)
  --mongo            Enable MongoDB dual write
  --no-mongo         Disable MongoDB (default)

Examples:
  node parser.js "D:/AshAndVeil_recent/PPM/Assets/Scripts" RPG --project AshAndVeil --mongo
  node parser.js "E:/AIMED/Luffy_Modify/Project/Assets/Scripts" Idle --project IdleMoney --mongo
`);
    process.exit(1);
}

const sourcePath = args[0];
const genre = args[1];
let projectName = path.basename(path.resolve(sourcePath, '..'));
let dbPath = 'E:/AI/db';
let mongoEnabled = false;

for (let i = 2; i < args.length; i++) {
    if (args[i] === '--project' && args[i + 1]) { projectName = args[++i]; }
    else if (args[i] === '--db' && args[i + 1]) { dbPath = args[++i]; }
    else if (args[i] === '--mongo') { mongoEnabled = true; }
    else if (args[i] === '--no-mongo') { mongoEnabled = false; }
}

parseProject(sourcePath, genre, dbPath, projectName, mongoEnabled)
    .then(() => process.exit(0))
    .catch(e => { console.error(e); process.exit(1); });
