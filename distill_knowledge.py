import os
from datetime import datetime
from openai import OpenAI

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

print("⏳ 正在启动大脑提纯引擎...")
if not os.path.exists('knowledge.txt'):
    print("⚠️ 找不到知识库，跳过提纯。")
    exit()

with open('knowledge.txt', 'r', encoding='utf-8') as f:
    knowledge_text = f.read()

if len(knowledge_text) < 2000:
    print("✅ 知识库还不够臃肿，无需提纯。")
    exit()

print(f"⏳ 当前知识库大小: {len(knowledge_text)} 字，开始提炼...")

prompt = f"""你是一位顶级的足球风控总监，现在需要对你的“经验记忆库”进行压缩提纯。
以下是过去积累的所有经验（可能包含了大量重复的、或者已经被优化过的废话）：
{knowledge_text[:8000]} ... (内容过长截取前部)

**任务**：请将这些经验，提炼成不超过 10 条【最高频、最致命、最可直接用于代码判断】的铁律。
要求：
1. 必须分类（如：情报缺失类、赔率异常类、联赛风格类）。
2. 每一条必须极其精炼，直指核心。
3. 输出格式直接作为新知识库的覆盖内容，不要多余的废话。"""

try:
    response = llm_client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        stream=False
    )
    distilled = response.choices[0].message.content.strip()
    
    # 备份老知识库（可选）
    os.rename('knowledge.txt', f'knowledge_backup_{datetime.now().strftime("%Y%m%d")}.txt')
    
    # 写入新知识库
    with open('knowledge.txt', 'w', encoding='utf-8') as f:
        f.write(f"--- 知识库提纯于 {datetime.now().strftime('%Y-%m-%d')} ---\n")
        f.write(distilled)
    print(f"✅ 提纯完毕！新知识库大小: {len(distilled)} 字。")
except Exception as e:
    print(f"❌ 提纯失败: {e}")
