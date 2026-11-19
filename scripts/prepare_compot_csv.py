"""
将 Zenodo 下载的 The Commercial Potential of Science 全量 CSV
裁剪为适合 ModelScope 创空间 Git 仓库体积的轻量切片（仅保留 doi, compot, scipot）。
"""
import argparse
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="原始 CSV 路径")
    parser.add_argument("--output", default="data/commercial_potential.csv", help="输出路径")
    parser.add_argument("--max-rows", type=int, default=200000, help="保留最大行数（按 compot 降序或高潜力筛选）")
    parser.add_argument("--min-compot", type=float, default=0.0, help="可选最小 compot 阈值")
    args = parser.parse_args()

    chunks = []
    for chunk in pd.read_csv(args.input, usecols=lambda c: c.lower() in {"doi", "compot", "scipot"}, chunksize=100000):
        chunk.columns = [c.lower() for c in chunk.columns]
        chunk = chunk.dropna(subset=["doi", "compot"])
        if args.min_compot > 0:
            chunk = chunk[chunk["compot"] >= args.min_compot]
        chunks.append(chunk)

    df = pd.concat(chunks, ignore_index=True)
    df = df.sort_values(by="compot", ascending=False).head(args.max_rows)
    df.to_csv(args.output, index=False)
    print(f"已导出 {len(df)} 条记录至 {args.output}")


if __name__ == "__main__":
    main()