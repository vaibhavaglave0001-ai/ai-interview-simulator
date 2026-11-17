"""Curated concepts and scoring guidance; independent of network services.

Each domain has twelve distinct concepts at each difficulty. Difficulty prompts
ask for foundations, application, or analysis rather than repeating a concept
within a session. Topic keys let the selector favor conceptual variety.
"""

DOMAINS = {
    "python": "Python", "java": "Java", "cpp": "C++",
    "dsa": "Data Structures and Algorithms", "dbms": "DBMS",
    "os": "Operating Systems", "networks": "Computer Networks",
    "ai": "Artificial Intelligence", "ml": "Machine Learning",
    "web": "Web Development",
}

# topic | focused question | ideal answer
CONTENT = {
"python": """
mutability|How do Python lists differ from tuples?|Lists are mutable sequences; tuples are immutable sequences. Choose based on whether the collection must change.
generators|How does a Python generator produce values?|A generator uses yield to suspend execution and produces values lazily, reducing memory use for streaming workloads.
mapping|How do you safely retrieve a missing dictionary key?|Use get with a default or handle KeyError. A dictionary maps hashable keys to values using a hash table.
exceptions|How should Python code handle exceptions?|Catch specific exceptions, preserve useful context, and use finally for cleanup. Avoid swallowing unexpected errors.
resources|What does a Python context manager do?|The with statement calls enter and exit methods to manage acquisition and cleanup even when an exception occurs.
decorators|How does a Python decorator wrap a function?|A decorator accepts a function and returns a callable adding behavior; functools.wraps preserves metadata.
scope|How does Python resolve variable scope?|LEGB searches local, enclosing, global, then built-in scopes. global and nonlocal explicitly change assignment targets.
copying|How do shallow and deep copies differ in Python?|A shallow copy shares nested objects; deepcopy recursively copies them. Consider aliasing, cycles and copying cost.
concurrency|When should Python use threads rather than processes?|Threads suit blocking I/O; processes can parallelize CPU work. Consider interpreter GIL behavior, serialization and synchronization costs.
sorting|How can you sort Python records by a field?|Use sorted or list.sort with a key function. Python sorting is stable and a tuple key can express multiple criteria.
imports|How do Python modules and packages organize code?|Modules contain reusable code; packages group modules. Use explicit imports and avoid circular dependencies and import side effects.
testing|How would you test a Python function with external dependencies?|Separate logic from I/O, inject or mock external dependencies, and test representative inputs, boundaries and failures.
""",
"java": """
equality|How do equals and == differ for Java objects?|The == operator compares references; equals expresses logical equality. Override hashCode consistently when overriding equals.
collections|When would you choose ArrayList over LinkedList?|ArrayList offers fast indexed access and cache locality; LinkedList has node overhead and linear access. Measure actual insertion patterns.
interfaces|How do Java interfaces differ from abstract classes?|Interfaces define contracts and support multiple implementations; abstract classes can share state and constructors with a single class hierarchy.
exceptions|How do checked and unchecked Java exceptions differ?|Checked exceptions must be caught or declared; unchecked exceptions derive from RuntimeException and often indicate programming errors.
memory|How does Java garbage collection reclaim objects?|The collector traces reachability from roots and reclaims unreachable objects. Long-lived references can cause leaks even with GC.
generics|Why does Java use generics?|Generics provide compile-time type safety and reusable algorithms. Type erasure limits runtime type information and primitive type arguments.
threads|How does synchronized protect Java shared state?|It provides mutual exclusion and visibility for the same monitor. Keep lock scopes small and maintain consistent lock ordering.
streams|What does a Java stream pipeline do?|Streams compose lazy intermediate operations and terminal operations over a source. Avoid mutable side effects and unnecessary parallelism.
immutability|How would you design an immutable Java class?|Use private final fields, validate construction, prevent subclass mutation and defensively copy mutable inputs and outputs.
resources|How does Java try-with-resources prevent resource leaks?|It closes AutoCloseable resources automatically in reverse order, including on exceptions, while preserving suppressed exceptions.
jvm|What is the relationship between Java bytecode and the JVM?|The compiler emits portable bytecode; the JVM loads, verifies and executes it using interpretation and JIT compilation.
maps|How does HashMap differ from ConcurrentHashMap?|HashMap requires external synchronization for concurrent mutation. ConcurrentHashMap supports concurrent access with atomic compound operations.
""",
"cpp": """
ownership|How does RAII manage C++ resources?|Bind resource ownership to object lifetime and release in destructors so scope exit and exceptions trigger cleanup.
pointers|When should C++ use unique_ptr rather than shared_ptr?|unique_ptr expresses exclusive ownership with move semantics; shared_ptr adds reference-counted shared ownership and can require weak_ptr to break cycles.
references|How do C++ references differ from pointers?|References alias existing objects and cannot be reseated; pointers can be null and reassigned. Both can dangle if lifetimes are invalid.
move|What do move semantics achieve in C++?|Moves transfer resources from expiring objects instead of copying. std::move enables move overload resolution but does not itself move anything.
virtual|Why should a polymorphic C++ base have a virtual destructor?|Deleting a derived object through a base pointer needs a virtual destructor to run the complete destructor chain correctly.
containers|When would you use vector rather than list in C++?|vector stores contiguous elements with fast access and cache locality; list offers stable node iterators with allocation and traversal overhead.
templates|How do C++ templates support generic programming?|Templates generate type-specific code at compile time. Constrain requirements and consider diagnostics, compilation time and code size.
const|What does const correctness communicate in C++?|Const restricts mutation through an interface, distinguishes read-only methods and references, and helps the compiler enforce intent.
exceptions|What is the strong exception guarantee in C++?|An operation either succeeds or leaves observable state unchanged. Build temporary state and commit using nonthrowing operations.
iterators|What can invalidate a C++ vector iterator?|Reallocation invalidates all iterators; insertion or erasure can invalidate iterators at or after the modification. Reserve capacity when appropriate.
threads|How do C++ mutexes prevent data races?|Protect all accesses to shared mutable state with consistent synchronization. Use lock_guard or scoped_lock for exception-safe locking.
values|How do stack and dynamic object lifetimes differ in C++?|Automatic objects die at scope exit; dynamic objects live until their owner releases them. Prefer explicit ownership over raw new and delete.
""",
"dsa": """
complexity|How do you analyze time and space complexity?|Count dominant operations and auxiliary storage as input grows. Distinguish worst-case, average-case and amortized bounds.
binary-search|What invariant makes binary search correct?|Maintain a sorted search interval containing all possible answers, shrink it on each step and handle boundaries consistently for logarithmic search.
hashing|How does a hash table resolve collisions?|Use chaining or probing and control load factor. Expected constant operations can degrade with poor hash distribution.
stacks|When would a stack be useful in an algorithm?|A stack implements last-in-first-out order for parsing, undo or DFS. Track the invariant represented by each stored element.
queues|How does a queue support breadth-first search?|FIFO ordering processes vertices by distance layers. Mark visited on enqueue to avoid duplicate work and cycles.
trees|What property makes a binary search tree useful?|Left keys precede the node and right keys follow it. Balanced trees maintain logarithmic operations while skewed trees can become linear.
heaps|How can a heap find the largest k values?|Maintain a min-heap of size k and replace the minimum when a larger value arrives, using O(n log k) time and O(k) space.
graphs|How would you detect a cycle in a directed graph?|Use DFS recursion-state colors or topological sorting with indegrees. A back edge or unprocessed vertices indicates a cycle.
dynamic-programming|When is dynamic programming appropriate?|Use overlapping subproblems and optimal substructure. Define state, recurrence, base cases and evaluation order before optimizing memory.
greedy|How do you justify a greedy algorithm?|Prove that the local choice can belong to an optimal solution using an exchange argument or invariant; test counterexamples first.
sorting|How do merge sort and quicksort compare?|Merge sort guarantees O(n log n) with extra storage and stability; quicksort is often efficient but can degrade to quadratic time without safeguards.
linked-lists|How would you detect a linked-list cycle without extra storage?|Use Floyd's slow and fast pointers. They meet inside a cycle and use constant auxiliary space.
""",
"dbms": """
normalization|Why normalize relational tables?|Separate functional dependencies to reduce update, insertion and deletion anomalies. Balance integrity against measured query costs.
indexes|How does a database index speed up a query?|An index narrows matching rows using an ordered or hashed structure but costs storage and write maintenance. Check the execution plan.
transactions|What do ACID transaction properties guarantee?|Atomicity groups changes, consistency preserves constraints, isolation governs interference and durability preserves committed data.
joins|How do inner and left joins differ?|An inner join returns matching rows; a left join retains all left rows and nulls unmatched right columns. Consider predicate placement.
isolation|What is a nonrepeatable read?|A transaction rereads a row and observes another transaction's committed change. Appropriate isolation or versioned snapshots can prevent it.
keys|How do primary and foreign keys protect data?|A primary key uniquely identifies rows; foreign keys enforce valid references. Specify deliberate deletion and update behavior.
aggregation|How do WHERE and HAVING differ in SQL?|WHERE filters input rows before grouping; HAVING filters aggregate groups. Understand null handling and grouping columns.
deadlocks|How can database transactions deadlock?|Transactions wait cyclically for locks. Use consistent access order, short transactions and bounded retries after victim rollback.
plans|How would you diagnose a slow SQL query?|Inspect an execution plan, row estimates and actual work. Check selective indexes, joins, excessive scans and stale statistics.
replication|How do replication and sharding differ?|Replication copies data for availability or reads; sharding partitions data for capacity. Consider lag, routing and cross-shard operations.
pagination|Why can keyset pagination outperform OFFSET?|Seek from an indexed stable ordering key instead of scanning skipped rows. Use a unique tie breaker and define behavior under concurrent changes.
constraints|When should a database enforce a uniqueness constraint?|Enforce business invariants atomically at the database boundary; application prechecks alone race. Handle duplicate constraint errors clearly.
""",
"os": """
processes|How do processes differ from threads?|Processes isolate address spaces; threads share process memory. Consider creation costs, communication and synchronization.
scheduling|How does round-robin CPU scheduling work?|Each ready task receives a time quantum. Small quanta improve responsiveness but add context-switch overhead.
virtual-memory|What does virtual memory provide?|Address translation isolates processes and maps virtual pages to physical frames or backing storage, supporting protection and flexible allocation.
paging|What happens during a page fault?|The OS checks access validity, locates or allocates a page, updates mappings and resumes execution; invalid access may terminate the process.
deadlocks|What conditions permit an operating-system deadlock?|Mutual exclusion, hold-and-wait, no preemption and circular wait must coexist. Break a condition or detect and recover.
synchronization|How does a semaphore differ from a mutex?|A mutex has ownership and protects critical sections; a semaphore counts permits and can coordinate resource availability or signaling.
context-switch|What state must a context switch preserve?|Save and restore registers, program counter and scheduling state; address-space switches may also affect translation caches.
files|How do file descriptors refer to open files?|A process descriptor indexes kernel open-file state including access mode and offset. Duplicated descriptors may share an offset.
system-calls|Why do applications use system calls?|System calls cross a controlled privilege boundary to request kernel services, with input validation and permission checks.
thrashing|Why can excessive paging cause thrashing?|Working sets exceed available frames and tasks spend time faulting instead of computing. Reduce memory pressure or active workloads.
ipc|How can independent processes communicate?|Use pipes, sockets, messages or shared memory. Choose based on isolation, throughput and synchronization requirements.
starvation|How does starvation differ from deadlock?|Starvation indefinitely denies a task progress while others run; deadlock is cyclic waiting. Fair scheduling and aging can reduce starvation.
""",
"networks": """
tcp-udp|How do TCP and UDP differ?|TCP offers ordered reliable byte streams with congestion control; UDP sends independent datagrams without built-in delivery guarantees.
dns|How does DNS resolve a hostname?|A resolver queries caches and authoritative servers through the DNS hierarchy. TTL controls caching and records map names to destinations.
routing|How does a router choose a packet's next hop?|It uses a routing table and longest-prefix match, then forwards toward a next hop while decrementing the packet hop limit.
subnets|Why divide an IP network into subnets?|Prefixes partition address ranges for routing, administration and isolation. Calculate host ranges from prefix length and address family.
handshake|What does the TCP three-way handshake establish?|SYN, SYN-ACK and ACK synchronize initial sequence numbers and confirm bidirectional reachability before data transfer.
tls|How does TLS protect network communication?|Authenticate the peer using certificates, negotiate keys and encrypt authenticated records. Validate hostnames and certificate trust.
congestion|How does congestion control differ from flow control?|Congestion control protects the network path; flow control protects the receiver's buffer. TCP adjusts sending using both limits.
nat|What does network address translation do?|NAT rewrites address and often port mappings between networks. It complicates unsolicited inbound connections and end-to-end addressing.
arp|How does ARP support IPv4 delivery on a local network?|ARP discovers a next-hop IPv4 address's link-layer address with local requests and cached responses. It is vulnerable to spoofing.
layers|Why use a layered network architecture?|Layers separate responsibilities such as framing, routing and transport, enabling interoperable protocols and systematic fault diagnosis.
latency|How would you investigate high network latency?|Measure round trips, loss, DNS and connection setup; compare routes and endpoints and distinguish propagation from queueing and server time.
load-balancing|How does a network load balancer distribute traffic?|Select healthy backends using a policy, perform health checks and manage connection or session affinity according to protocol requirements.
""",
"ai": """
search|How do breadth-first and depth-first AI search differ?|Breadth-first explores shallow states first and can find shortest unit-cost paths; depth-first uses less frontier memory but needs cycle safeguards.
heuristics|What makes an A-star heuristic admissible?|It never overestimates remaining optimal cost. With appropriate graph-search conditions, A-star can find an optimal path.
minimax|How does minimax choose a game move?|Alternate maximizing and minimizing utilities over possible moves. Alpha-beta pruning skips branches that cannot change the decision.
knowledge|How can an AI represent structured knowledge?|Use logical rules, graphs or ontologies with explicit entities and relations. Discuss inference, consistency and incomplete information.
uncertainty|How does Bayesian inference update a belief?|Combine likelihood with prior and normalize by evidence to obtain a posterior. State assumptions and assess sensitivity to the prior.
planning|How does an AI planner reach a goal?|Represent states, actions, preconditions and effects, then search for a valid sequence while considering costs and constraints.
reinforcement|How does reinforcement learning use rewards?|An agent learns a policy from interactions to maximize expected return, balancing exploration and exploitation under delayed feedback.
language|Why is tokenization important for language AI?|It converts text into model units and affects vocabulary coverage, sequence length and handling of unfamiliar or multilingual inputs.
vision|How does an AI image classifier use visual features?|Learn representations from labeled images, preserve spatial patterns and evaluate robustness to lighting, shifts and distribution changes.
fairness|How would you assess bias in an AI decision system?|Audit data and subgroup outcomes, select context-appropriate fairness metrics and evaluate trade-offs with affected stakeholders.
explainability|How would you explain an AI prediction to a user?|Provide faithful evidence, limitations and actionable context. Distinguish interpretable models from approximate post-hoc explanations.
retrieval|How can retrieval improve a generative AI answer?|Retrieve relevant trusted documents, supply context and cite evidence. Evaluate retrieval quality and avoid treating retrieved text as instructions.
""",
"ml": """
supervision|How do supervised and unsupervised learning differ?|Supervised learning uses labeled targets; unsupervised learning discovers structure without target labels. Choose evaluation appropriate to the objective.
overfitting|How can you detect and reduce overfitting?|Compare training and validation performance, use cross-validation, regularization or simpler models, and collect representative data.
splits|Why separate training, validation and test data?|Fit parameters on training data, tune on validation data and reserve test data for final estimation without leakage.
metrics|When is precision more useful than accuracy?|Precision measures the fraction of predicted positives that are correct. Consider false-positive costs and combine with recall for imbalanced classes.
regularization|How do L1 and L2 regularization affect models?|L1 can produce sparse coefficients; L2 shrinks coefficients smoothly. Tune penalty strength using validation on appropriately scaled data.
gradient|How does gradient descent optimize a model?|Iteratively update parameters opposite the loss gradient. Learning rate, scaling and batch noise influence convergence and stability.
features|Why should preprocessing be fitted only on training data?|Fitting imputers, scalers or feature selection on held-out data leaks information. Use pipelines and apply trained transformations consistently.
trees|How does a random forest combine decision trees?|Train diversified trees using bootstrap samples and feature subsets, then aggregate predictions to reduce variance.
imbalance|How can you handle a rare positive class?|Use stratified validation, relevant metrics, class weights or resampling within training folds and choose a threshold based on costs.
drift|How would you detect model degradation after deployment?|Monitor input and prediction shifts plus delayed labeled performance. Distinguish data drift from changed relationships and retrain when justified.
clustering|How does k-means form clusters?|Alternate assignment to nearest centroids and centroid updates to reduce within-cluster squared distance. Scale features and consider non-spherical clusters.
calibration|What does probability calibration measure?|Predicted probabilities should match empirical outcome frequencies. Evaluate reliability and use held-out calibration without test leakage.
""",
"web": """
http|How do HTTP GET and POST differ?|GET retrieves representations and is safe and idempotent; POST submits processing and may change state. Define caching and retry behavior carefully.
css|How does the CSS box model determine element size?|Content, padding, border and margin define layout; border-box includes padding and border in the declared dimensions.
dom|How does event delegation work in a browser?|Listen on an ancestor and inspect the event target as events bubble, allowing handlers for dynamically added children.
async|How do JavaScript promises coordinate asynchronous work?|A promise settles once with a value or error. Chain or await it and handle rejections without blocking the event loop.
accessibility|How would you make a web form accessible?|Use associated labels, semantic controls, keyboard access, clear validation and announced status updates with sensible focus behavior.
xss|How do you prevent cross-site scripting?|Escape output for its context, use safe DOM APIs and sanitize permitted HTML. Content security policy adds defense in depth.
csrf|Why do cookie-authenticated forms need CSRF protection?|Browsers attach cookies to requests automatically. Validate unpredictable request tokens and use appropriate same-site cookie policies.
sessions|How should a web application manage login sessions?|Use unpredictable signed or server-managed sessions, secure cookie flags, rotation after login, expiration and server-side authorization on every request.
cors|What does CORS control in a browser?|Response headers allow selected origins to read cross-origin responses. CORS is not authentication and credentialed access requires explicit origins.
caching|How can HTTP caching reduce repeated downloads?|Use cache-control freshness and validators such as ETag with conditional requests. Avoid sharing private authenticated responses.
responsive|How would you build a responsive web layout?|Use flexible grids, relative sizing and media queries, then test content, keyboard use and overflow across viewport widths.
api-errors|How should a frontend handle a failed API request?|Show actionable errors, preserve input and use bounded retries only for safe operations. Distinguish loading, empty, failure and success states.
""",
}

HR = """
introduction|Tell me about yourself and the experience most relevant to this role.|Connect background, relevant skills and motivation in a concise introduction with specific evidence.
strengths|What strength would help you contribute to this team?|Name a relevant strength and support it with a specific example and outcome.
weaknesses|What skill are you actively working to improve?|Identify an honest development area, actions taken and evidence of progress without presenting a disguised strength.
career|Where would you like your career to develop over the next few years?|Connect realistic growth goals with the role, learning plans and contributions to the organization.
teamwork|Describe a time you helped a team achieve a shared goal.|Use situation, task, personal action and result; explain collaboration and give colleagues appropriate credit.
leadership|Tell me about a time you led without formal authority.|Explain how you established trust, aligned people, handled resistance and measured the outcome.
conflict|How did you resolve a disagreement with a colleague?|Listen to the other perspective, establish shared goals, discuss facts respectfully and agree on follow-up actions.
problem-solving|Describe an unfamiliar problem you solved with limited information.|Clarify the goal, gather evidence, test assumptions, compare options and explain the result and lessons.
priorities|Two stakeholders ask for urgent work at the same time. What would you do?|Assess impact and deadlines, agree priorities with stakeholders and communicate trade-offs and realistic commitments.
feedback|Tell me about feedback that changed how you work.|Describe the feedback, receive it constructively, implement a concrete change and show its impact.
failure|Describe a commitment you missed and how you responded.|Take responsibility, explain the impact, communicate promptly and show recovery and prevention steps.
adaptability|How did you adapt when a project's requirements changed unexpectedly?|Clarify the new goal, reassess plans, communicate changes and support colleagues through the transition.
ethics|What would you do if asked to hide a mistake from a customer?|Establish facts, explain the risks, follow appropriate escalation and communicate honestly while protecting sensitive information.
initiative|Tell me about an improvement you initiated without being asked.|Explain the opportunity, how you gained support, the action taken and measurable benefits.
motivation|What aspects of this role would keep you motivated during difficult work?|Connect genuine interests and values to the role and describe practical habits for sustaining effort through setbacks.
"""


def bank_rows():
    for category, domain, content in [("hr", "", HR)] + [
        ("technical", domain, content) for domain, content in CONTENT.items()
    ]:
        for line in content.strip().splitlines():
            topic, question, answer = line.split("|")
            for difficulty in ("easy", "medium", "hard"):
                suffix = {
                    "easy": "",
                    "medium": " Include a concrete example and explain your reasoning.",
                    "hard": " Analyze constraints, trade-offs, and how you would assess the outcome.",
                }[difficulty]
                yield (question + suffix, category, difficulty, answer, domain, topic)
