from flashrank import Ranker, RerankRequest

ranker = Ranker(model_name='ms-marco-MiniLM-L-12-v2', cache_dir='/tmp')
passage = 'Thủ tướng Việt Nam và Thủ tướng Lào đã trao đổi về một số vướng mắc trong hợp tác kinh tế giữa hai nước.'

q1 = 'Hợp tác kinh tế Việt Nam và Lào'
q2 = 'Công thức nấu phở bò gia truyền'
q3 = 'Bí quyết du hành vũ trụ lên sao Hỏa'

for q in [q1, q2, q3]:
    req = RerankRequest(query=q, passages=[{'id': 1, 'text': passage}])
    res = ranker.rerank(req)
    print(f"Query: '{q}' -> FlashRank score: {res[0]['score']}")
