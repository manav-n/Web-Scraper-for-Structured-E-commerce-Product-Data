# utils/visualization.py
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Set Agg backend to avoid GUI issues
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud
import re
import os
import contextlib
from pathlib import Path
import zipfile

def generate_visualizations(data, search_term, timestamp):
    try:
        df = pd.DataFrame(data)
        visualization_dir = str(Path.home() / "Downloads")
        os.makedirs(visualization_dir, exist_ok=True)

        # 1. Word Cloud for 'title'
        def generate_wordcloud(df, search_term, timestamp):
            try:
                # Cleanup existing files before generating new ones
                with contextlib.suppress(FileNotFoundError):
                    os.remove(f"{visualization_dir}/wordcloud_{search_term}_{timestamp}.png")
                
                if 'title' not in df.columns or df['title'].isnull().all():
                    print("Skipping wordcloud chart: 'title' column missing or empty.")
                    return None

                titles = df['title'].dropna().astype(str).tolist()
                if not titles:
                    print("Skipping wordcloud chart: No valid titles found.")
                    return None
                
                
                combined_titles = " ".join(titles)
                cleaned_titles = re.sub(r'[^A-Za-z\s]', '', combined_titles)  # Remove numbers and special chars
                wordcloud = WordCloud(width=1000, height=800, background_color="white").generate(cleaned_titles)

                plt.figure(figsize=(10, 8))
                plt.imshow(wordcloud, interpolation="bilinear")
                plt.axis("off")
                plt.title("Most Frequent Words in Product Titles", fontsize=20, pad=40)   # Adjust title position (1.0 is default)
                plt.tight_layout()  # Adjust layout to prevent cutoff
                wordcloud_filename = f"wordcloud_{search_term}_{timestamp}.png"
                plt.savefig(os.path.join(visualization_dir, wordcloud_filename), dpi=100)
                plt.close()
                return wordcloud_filename

            except Exception as e:
                print(f"Skipping wordcloud chart: {e}")
                return None

        # 2. Price Distribution Histogram (Dynamic Bins)
        def plot_price_distribution(df, search_term, timestamp):
            try:
                # Cleanup existing files before generating new ones
                with contextlib.suppress(FileNotFoundError):
                    os.remove(f"{visualization_dir}/price_distribution_{search_term}_{timestamp}.png")
                    
                df['discounted_price'] = pd.to_numeric(df['discounted_price'], errors='coerce')

                # Calculate min and max dynamically
                min_price = df['discounted_price'].min()
                max_price = df['discounted_price'].max()

                if pd.isna(min_price) or pd.isna(max_price) or min_price == max_price:
                    print("Insufficient price data to generate distribution.")
                    return None

                # Automatically determine bin count (10 bins or adjust based on spread)
                bin_count = 10  # Default
                price_range = max_price - min_price

                if price_range > 20000:
                    bin_count = 20  # More bins for wide price ranges
                elif price_range < 5000:
                    bin_count = 8  # Fewer bins for narrow ranges

                bin_size = (max_price - min_price) / bin_count
                bins = [min_price + i * bin_size for i in range(bin_count + 1)]
                labels = [f"{int(bins[i])}-{int(bins[i + 1])}" for i in range(len(bins) - 1)]

                # Create a price range column
                df['price_range'] = pd.cut(df['discounted_price'], bins=bins, labels=labels, right=False)

                # Plot histogram
                plt.figure(figsize=(10, 8))
                df['price_range'].value_counts().sort_index().plot(kind='bar', color='skyblue')
                plt.title("Price Distribution of Products", fontsize=20, pad=40)
                plt.xlabel("Price Range (₹)", fontsize=16, labelpad=25)
                plt.ylabel("Number of Products", fontsize=16, labelpad=25)
                plt.xticks(rotation=45, ha='right', fontsize=14)
                plt.yticks(fontsize=14)
                plt.tight_layout()  # Adjust layout to prevent cutoff
                price_distribution_filename = f"price_distribution_{search_term}_{timestamp}.png"
                plt.savefig(os.path.join(visualization_dir, price_distribution_filename))
                plt.close()
                return price_distribution_filename

            except Exception as e:
                print(f"Skipping price distribution chart: {e}")
                return None

        # 3. Price vs Ratings Scatter Plot
        def plot_price_vs_ratings(df, search_term, timestamp):
            try:
                # Cleanup existing files before generating new ones
                with contextlib.suppress(FileNotFoundError):
                    os.remove(f"{visualization_dir}/price_vs_ratings_{search_term}_{timestamp}.png")
                    
                df['discounted_price'] = pd.to_numeric(df['discounted_price'], errors='coerce')
                df['rating'] = pd.to_numeric(df['rating'], errors='coerce')

                plt.figure(figsize=(10, 8))
                plt.tight_layout()   # Adjust layout to prevent overlap (cut-off labels)
                plt.scatter(df['discounted_price'], df['rating'], c='blue', alpha=0.5)
                plt.title("Price vs Ratings", fontsize=20, pad=40)
                plt.xlabel("Discounted Price (₹)", fontsize=16, labelpad=25)
                plt.ylabel("Ratings", fontsize=16, labelpad=25)
                plt.xticks(fontsize=14)
                plt.yticks(fontsize=14)
                plt.grid(True)
                plt.tight_layout()  # Adjust layout to prevent overlap
                price_vs_ratings_filename = f"price_vs_ratings_{search_term}_{timestamp}.png"
                plt.savefig(os.path.join(visualization_dir, price_vs_ratings_filename))
                plt.close()
                return price_vs_ratings_filename

            except Exception as e:
                print(f"Skipping price vs rating chart: {e}")
                return None

        # 4. Top Brands by Reviews Count
        def plot_top_brands_by_reviews(df, search_term, timestamp):
            try:
                # Cleanup existing files before generating new ones
                with contextlib.suppress(FileNotFoundError):
                    os.remove(f"{visualization_dir}/top_brands_{search_term}_{timestamp}.png")
                    
                df['reviews_count'] = pd.to_numeric(df['reviews_count'], errors='coerce')

                top_brands = df.groupby('brand_name')['reviews_count'].sum().sort_values(ascending=False).head(10)

                plt.figure(figsize=(10, 8))
                top_brands.plot(kind='bar', color='orange')
                plt.title("Top Brands by Total Reviews Count", fontsize=20, pad=40)
                plt.xlabel("Brand Name", fontsize=16, labelpad=25)
                plt.ylabel("Total Reviews", fontsize=16, labelpad=25)
                plt.xticks(rotation=90, fontsize=14)
                plt.yticks(fontsize=14)
                plt.tight_layout()  # Adjust layout to prevent overlap and cutoff
                top_brands_filename = f"top_brands_{search_term}_{timestamp}.png"
                plt.savefig(os.path.join(visualization_dir, top_brands_filename))
                plt.close()
                return top_brands_filename

            except Exception as e:
                print(f"Skipping brands by reviews chart: {e}")
                return None

        # 5. Amazon Heatmap - Ratings vs Discount % (with Sales Gradient)
        def plot_heatmap(df, search_term, timestamp):
            try:
                # Cleanup existing files before generating new ones
                with contextlib.suppress(FileNotFoundError):
                    os.remove(f"{visualization_dir}/heatmap_{search_term}_{timestamp}.png")
                    
                df['discount_percentage'] = pd.to_numeric(df['discount_percentage'].str.replace('%', ''), errors='coerce')
                df['last_month_sales'] = pd.to_numeric(df['last_month_sales'].str.replace('+', ''), errors='coerce').replace(0, np.nan)  # Convert 0 to NaN
                df['rating'] = pd.to_numeric(df['rating'], errors='coerce')

                # Sort values for better visualization
                df = df.sort_values(by=['rating', 'discount_percentage'], ascending=[True, True])

                # Replace missing 'last_month_sales' with NaN (no zeros)
                df['last_month_sales'] = df['last_month_sales'].fillna(np.nan)

                # Create pivot table (WITHOUT fill_value=0)
                heatmap_data = df.pivot_table(index='rating', columns='discount_percentage', values='last_month_sales',
                                              aggfunc='sum')
                
                # Replace 0 values in the pivot table with NaN
                heatmap_data = heatmap_data.replace(0, np.nan)

                # Create a mask for missing values (includes NaN and 0)
                mask = heatmap_data.isnull()

                # Set base figure size and adjust if needed
                base_fig_width, base_fig_height = 10, 8
                fig_width_user = min(16, max(10, int(0.75 * heatmap_data.shape[1])))
                fig_height_user = min(12, max(8, int(0.75 * heatmap_data.shape[0])))

                # Cap the size at (10, 8) to maintain consistency
                fig_width = min(base_fig_width, fig_width_user)
                fig_height = min(base_fig_height, fig_height_user)
                
                # Calculate font size based on box density
                n_rows, n_cols = heatmap_data.shape
                box_area = n_rows * n_cols
                font_size = max(6, min(14, int(200 / (box_area if box_area > 0 else 1))))

                plt.figure(figsize=(fig_width, fig_height))

                # Draw heatmap
                sns.heatmap(heatmap_data, cmap="viridis", fmt='.0f', annot=True, linewidths=0.5, linecolor='gray',
                            cbar_kws={'label': 'Last Month Sales'}, mask=mask, annot_kws={"size": font_size})  # Reduce font size for annotations

                # Get the color bar's axis and adjust label properties
                cb_ax = plt.gcf().axes[-1]  # Last axis is the color bar
                cb_ax.set_ylabel('Last Month Sales', fontsize=14, labelpad=15)  # Set font size and padding
                
                plt.title("Sales Heatmap (Ratings vs Discount %)", fontsize=20, pad=40)
                plt.xlabel("Discount Percentage", fontsize=16, labelpad=25)
                plt.ylabel("Ratings", fontsize=16, labelpad=25)

                # Rotate x-axis labels to prevent overlap
                plt.xticks(rotation=45, ha='right', fontsize=14)
                plt.yticks(rotation=0, fontsize=14)

                plt.tight_layout()  # Adjust layout to prevent overlap
                heatmap_filename = f"heatmap_{search_term}_{timestamp}.png"
                plt.savefig(os.path.join(visualization_dir, heatmap_filename))
                plt.close()
                return heatmap_filename

            except Exception as e:
                print(f"Skipping heatmap chart: {e}")
                return None

        # Generate all visualizations
        visualizations = {
            'wordcloud': generate_wordcloud(df, search_term, timestamp),
            'price_distribution': plot_price_distribution(df, search_term, timestamp),
            'price_vs_ratings': plot_price_vs_ratings(df, search_term, timestamp),
            'top_brands': plot_top_brands_by_reviews(df, search_term, timestamp),
            'heatmap': plot_heatmap(df, search_term, timestamp)
        }

        # Create ZIP Archive
        zip_filename = f"{search_term}_{timestamp}_visuals.zip"
        zip_path = os.path.join(str(Path.home() / "Downloads"), zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for key in visualizations:  # <--- key variable used here
                filename = visualizations[key]
                if filename:
                    file_path = os.path.join(str(Path.home() / "Downloads"), filename)
                    if os.path.exists(file_path):
                        zipf.write(file_path, arcname=os.path.basename(file_path))


        return visualizations, zip_filename


    except Exception as e:
        print(f"Error generating visualizations: {e}")
        return {}, None